import React, { useState, useEffect, useCallback } from 'react';
import { autoOptimize, createManualEvent, deleteManualEvent, getStations } from '../api/client';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  Calendar, CloudRain, Sun, Zap, Train, RefreshCw,
  ChevronLeft, ChevronRight, MapPin, Plus, X, Layers,
  AlertTriangle, AlertCircle, Info, Clock, CheckCircle2, ChevronDown
} from 'lucide-react';
import { getDateOffset, shiftDate, formatDate } from '../utils/dateUtils';

const VENUE_OPTIONS = [
  { key: 'uppal_stadium', name: 'Rajiv Gandhi Cricket Stadium, Uppal', lat: 17.4063, lon: 78.5480, nearest_stop_id: 'STD', distance_km: 0.7, capacity: 55000, default_url: 'https://in.bookmyshow.com/sports/ipl-sunrisers-hyderabad/ET00355125' },
  { key: 'hitex', name: 'Hitex Exhibition Centre, HITEC City', lat: 17.4517, lon: 78.3727, nearest_stop_id: 'HTC', distance_km: 1.2, capacity: 18000, default_url: 'https://in.bookmyshow.com/events/hitex-hyderabad/ET00391003' },
  { key: 'hicc', name: 'HICC / Novotel Convention Centre, Madhapur', lat: 17.4448, lon: 78.3766, nearest_stop_id: 'HTC', distance_km: 1.5, capacity: 8000, default_url: 'https://in.bookmyshow.com/events/global-cloud-summit-hyderabad/ET00391001' },
  { key: 'gachibowli_stadium', name: 'Gachibowli Indoor Stadium, IT Corridor', lat: 17.4399, lon: 78.3490, nearest_stop_id: 'RDG', distance_km: 2.0, capacity: 12000, default_url: 'https://in.bookmyshow.com/sports/pro-kabaddi-telugu-titans/ET00378910' },
  { key: 'shilpakala', name: 'Shilpakala Vedika, HITEC City', lat: 17.4503, lon: 78.3756, nearest_stop_id: 'HTC', distance_km: 0.8, capacity: 3500, default_url: 'https://in.bookmyshow.com/events/zakir-khan-live-standup/ET00344567' },
  { key: 'shilparamam', name: 'Shilparamam Arts & Crafts Village, Madhapur', lat: 17.4521, lon: 78.3712, nearest_stop_id: 'HTC', distance_km: 0.6, capacity: 6000, default_url: 'https://in.bookmyshow.com/explore/events-hyderabad?search=shilparamam' },
  { key: 'lb_stadium', name: 'Lal Bahadur Shastri Stadium, Basheerbagh', lat: 17.3997, lon: 78.4724, nearest_stop_id: 'ASM', distance_km: 0.6, capacity: 20000, default_url: 'https://in.bookmyshow.com/explore/events-hyderabad?search=lb+stadium' },
  { key: 'tank_bund', name: 'Tank Bund / Hussain Sagar Waterfront', lat: 17.4239, lon: 78.4738, nearest_stop_id: 'KHA', distance_km: 1.1, capacity: 15000, default_url: 'https://telanganatourism.gov.in/events/sunday-funday-tank-bund.html' },
  { key: 'jbs_grounds', name: 'JBS Parade Ground Grounds, Secunderabad', lat: 17.4445, lon: 78.4976, nearest_stop_id: 'JBS', distance_km: 0.3, capacity: 25000, default_url: 'https://in.bookmyshow.com/explore/events-hyderabad' },
  { key: 'custom', name: 'Custom Venue / Specific Metro Station', lat: 17.4374, lon: 78.4482, nearest_stop_id: 'AME', distance_km: 0.8, capacity: 10000, default_url: '' },
];

const CORRIDOR_META = {
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

const ChartTooltip = ({ active, payload, label, corridorInfo }) => {
  if (!active || !payload || !payload.length) return null;
  const item = payload[0]?.payload;
  if (!item) return null;

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3 shadow-xl text-xs space-y-1.5 min-w-[220px]">
      <div className="flex items-center justify-between border-b border-slate-800 pb-1 font-semibold text-slate-300">
        <span>⏰ {label}</span>
        <span className="text-slate-400 font-mono">GTFS Base: {item.Baseline}m</span>
      </div>
      <div className="flex justify-between text-cyan-300 font-medium">
        <span>Inbound ({corridorInfo?.inboundRoute || 'Inbound'}):</span>
        <span className="font-mono font-bold">{item.Inbound} min</span>
      </div>
      <div className="flex justify-between text-rose-300 font-medium">
        <span>Outbound ({corridorInfo?.outboundRoute || 'Outbound'}):</span>
        <span className="font-mono font-bold">{item.Outbound} min</span>
      </div>
      {item.Inbound < item.Baseline && (
        <div className="text-[11px] text-emerald-400 pt-1 border-t border-slate-800">
          ⚡ Compressed {(item.Baseline - Math.min(item.Inbound, item.Outbound)).toFixed(1)}m for commuter flow
        </div>
      )}
    </div>
  );
};

export default function AutoPilotDashboard({ onOpenEventMap }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [excludedIds, setExcludedIds] = useState([]);
  const [selectedCorridor, setSelectedCorridor] = useState('RED');
  const [activeTab, setActiveTab] = useState('directives'); // 'directives' | 'events' | 'table'
  const [selectedDate, setSelectedDate] = useState(getDateOffset(0));
  const [stations, setStations] = useState([]);

  // Load station list on mount
  useEffect(() => {
    getStations().then(res => {
      if (Array.isArray(res)) {
        setStations(res.slice().sort((a, b) => a.stop_name.localeCompare(b.stop_name)));
      }
    }).catch(err => console.warn('Could not load stations:', err));
  }, []);

  // Modal state
  const [showAddEventModal, setShowAddEventModal] = useState(false);
  const [addEventSubmitting, setAddEventSubmitting] = useState(false);
  const [newEvent, setNewEvent] = useState({
    name: '',
    event_type: 'Sports',
    venue_key: 'uppal_stadium',
    custom_venue_name: '',
    nearest_stop_id: 'STD',
    distance_to_nearest_metro_km: 0.7,
    venue_lat: 17.4063,
    venue_lon: 78.5480,
    date: getDateOffset(0),
    start_time: '19:00',
    end_time: '22:30',
    venue_capacity: 55000,
    ticket_price_avg: 800,
    user_interest_hearts: 25000,
    event_url: '',
  });

  const fetchOptimization = useCallback(async (excludeIds = [], dateStr = null) => {
    setLoading(true);
    setError(null);
    try {
      const result = await autoOptimize({
        exclude_event_ids: excludeIds,
        date: dateStr || selectedDate,
      });
      setData(result);
    } catch (err) {
      setError(err.message || 'Failed to fetch optimization');
      console.error('Auto-optimize error:', err);
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => {
    fetchOptimization(excludedIds, selectedDate);
  }, [selectedDate]);

  const handleRemoveEvent = async (ev) => {
    const eventId = typeof ev === 'object' ? (ev.id || ev.name) : ev;
    if (typeof ev === 'object' && ev.is_manual && ev.id) {
      try {
        await deleteManualEvent(ev.id);
      } catch (e) {
        console.warn('Failed to delete manual event:', e);
      }
    }
    const updated = [...excludedIds, String(eventId)];
    setExcludedIds(updated);
    fetchOptimization(updated, selectedDate);
  };

  const handleRestoreEvent = (eventId) => {
    const updated = excludedIds.filter(id => id !== String(eventId));
    setExcludedIds(updated);
    fetchOptimization(updated, selectedDate);
  };

  const handleCreateEvent = async (e) => {
    e.preventDefault();
    if (!newEvent.name.trim()) return;
    setAddEventSubmitting(true);
    try {
      const venueObj = VENUE_OPTIONS.find(v => v.key === newEvent.venue_key) || VENUE_OPTIONS[0];
      await createManualEvent({
        name: newEvent.name.trim(),
        event_type: newEvent.event_type.toLowerCase(),
        venue_name: newEvent.custom_venue_name || venueObj.name,
        venue_id: newEvent.venue_key,
        venue_lat: parseFloat(newEvent.venue_lat) || venueObj.lat,
        venue_lon: parseFloat(newEvent.venue_lon) || venueObj.lon,
        nearest_stop_id: newEvent.nearest_stop_id || venueObj.nearest_stop_id,
        distance_to_nearest_metro_km: parseFloat(newEvent.distance_to_nearest_metro_km) || 0.7,
        date: newEvent.date || selectedDate,
        start_time: `${newEvent.date || selectedDate}T${newEvent.start_time}:00`,
        end_time: `${newEvent.date || selectedDate}T${newEvent.end_time}:00`,
        venue_capacity: parseInt(newEvent.venue_capacity, 10) || 15000,
        ticket_price_avg: parseFloat(newEvent.ticket_price_avg) || 600,
        user_interest_hearts: parseInt(newEvent.user_interest_hearts, 10) || 15000,
        event_url: newEvent.event_url,
      });

      setShowAddEventModal(false);
      setNewEvent(prev => ({ ...prev, name: '', event_url: '' }));
      await fetchOptimization(excludedIds, selectedDate);
    } catch (err) {
      alert('Failed to add event: ' + (err.message || 'Unknown error'));
    } finally {
      setAddEventSubmitting(false);
    }
  };

  const corridorInfo = CORRIDOR_META[selectedCorridor] || CORRIDOR_META.RED;
  const corridorRows = data?.directional_headways?.[selectedCorridor] || [];
  const chartData = corridorRows.map(h => ({
    hour: `${String(h.hour).padStart(2, '0')}:00`,
    Inbound: h.inbound_headway,
    Outbound: h.outbound_headway,
    Baseline: h.baseline_headway,
    inbound_tph: h.inbound_tph,
    outbound_tph: h.outbound_tph,
    inbound_fraction: h.inbound_fraction,
    outbound_fraction: h.outbound_fraction,
  }));

  const isToday = selectedDate === getDateOffset(0);

  // Peak metrics for selected corridor
  const peakInbound = corridorRows.length ? Math.min(...corridorRows.map(r => r.inbound_headway)) : null;
  const peakOutbound = corridorRows.length ? Math.min(...corridorRows.map(r => r.outbound_headway)) : null;

  return (
    <div className="flex flex-col min-h-full space-y-6 pb-12">
      {/* ─── Top Header: Clear & Purposeful ─── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-800/80">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            <Train className="w-6 h-6 text-cyan-400" />
            Control Center
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Autonomous bidirectional headway optimization based on real-time event surges & weather.
          </p>
        </div>

        {/* Clean Controls Strip */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Compact Date Navigator */}
          <div className="inline-flex items-center rounded-xl bg-slate-900 border border-slate-800 p-1">
            <button
              onClick={() => setSelectedDate(shiftDate(selectedDate, -1))}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Previous Day"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <div className="px-3 text-xs font-semibold text-slate-200">
              {formatDate(selectedDate)}
            </div>
            <button
              onClick={() => setSelectedDate(shiftDate(selectedDate, 1))}
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
                : 'bg-slate-900 text-slate-400 border-slate-800 hover:text-white'
            }`}
          >
            Today
          </button>

          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded-xl px-2.5 py-1.5 focus:outline-none focus:border-cyan-500"
          />

          {/* Clean Proximity Map Button */}
          {onOpenEventMap && (
            <button
              onClick={onOpenEventMap}
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-xs font-semibold text-slate-200 transition shadow-sm active:scale-95"
            >
              <MapPin className="w-3.5 h-3.5 text-orange-400" />
              <span>Event Map</span>
            </button>
          )}

          {/* Re-optimize Button */}
          <button
            onClick={() => fetchOptimization(excludedIds, selectedDate)}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold transition shadow-md shadow-cyan-600/20 active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>{loading ? 'Optimizing...' : 'Re-optimize'}</span>
          </button>
        </div>
      </div>

      {/* ─── Operating Context Strip (Quiet single-line banner) ─── */}
      {data && (
        <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl px-4 py-2.5 flex flex-wrap items-center justify-between text-xs text-slate-300 gap-3">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              {data.weather?.is_rain ? <CloudRain className="w-4 h-4 text-blue-400" /> : <Sun className="w-4 h-4 text-amber-400" />}
              <span className="font-semibold text-slate-200">{data.weather?.temperature || 30}°C</span>
              <span className="text-slate-300">{data.weather?.description || 'Clear'}</span>
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                OpenWeather Live
              </span>
              {data.weather?.is_rain && (
                <span className="text-blue-300 font-semibold">(+{Math.round(((data.weather?.rain_surge_multiplier || 1.22) - 1) * 100)}% rain transit shift)</span>
              )}
            </div>

            {data.holiday_info?.is_holiday && (
              <span className="text-purple-300 font-medium">
                • 🎉 {data.holiday_info.holiday_name} (Bus terminal surge active)
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-slate-400">
            <span>⚡ <strong>{data.total_events || 0}</strong> events active</span>
            <span>• 🤖 <strong>{data.recommendations?.length || 0}</strong> dispatch directives</span>
          </div>
        </div>
      )}

      {/* ─── HERO SECTION: Full-Width Headway Optimization ─── */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
        {/* Corridor Selector & Operational Summary */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="w-3 h-3 rounded-full" style={{ backgroundColor: corridorInfo.color }}></span>
              <h2 className="text-lg font-bold text-white tracking-wide">
                {corridorInfo.name} Headway Optimization
              </h2>
              <span className="text-xs text-slate-400 font-mono">
                ({corridorInfo.terminals})
              </span>
            </div>
            {peakInbound && (
              <p className="text-xs text-slate-400 mt-1">
                Peak Inbound: <strong className="text-cyan-300">{peakInbound}m</strong> • Peak Outbound: <strong className="text-rose-300">{peakOutbound}m</strong>
              </p>
            )}
          </div>

          {/* Line Switcher */}
          <div className="inline-flex rounded-xl bg-slate-950/80 p-1 border border-slate-800">
            {['RED', 'BLUE', 'GREEN'].map(c => {
              const isSelected = selectedCorridor === c;
              const cfg = CORRIDOR_META[c];
              return (
                <button
                  key={c}
                  onClick={() => setSelectedCorridor(c)}
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
              Inbound: {corridorInfo.inboundRoute}
            </span>
            <span className="flex items-center gap-1.5 text-rose-300">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
              Outbound: {corridorInfo.outboundRoute}
            </span>
            <span className="flex items-center gap-1.5 text-slate-400">
              <span className="w-3 h-0.5 border-b border-dashed border-slate-500 inline-block" />
              Baseline GTFS
            </span>
          </div>

          <span className="text-[11px] text-slate-500 font-mono hidden sm:inline">
            Lower minutes = tighter spacing & more trains
          </span>
        </div>

        {/* Full-Width Chart */}
        <div style={{ height: '360px', width: '100%' }}>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="hour"
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
                <Tooltip content={<ChartTooltip corridorInfo={corridorInfo} />} />
                {/* Baseline GTFS Line */}
                <Line
                  type="monotone"
                  dataKey="Baseline"
                  stroke="#64748b"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                />
                {/* Inbound Line */}
                <Line
                  type="monotone"
                  dataKey="Inbound"
                  stroke="#38bdf8"
                  strokeWidth={3}
                  activeDot={{ r: 6, fill: '#38bdf8' }}
                  dot={{ r: 3, fill: '#38bdf8' }}
                />
                {/* Outbound Line */}
                <Line
                  type="monotone"
                  dataKey="Outbound"
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

      {/* ─── LOWER SECTION: Clean Segmented Workspaces (Tabs) ─── */}
      <div className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
        {/* Section Tabs */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('directives')}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition ${
                activeTab === 'directives'
                  ? 'bg-slate-800 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              AI Dispatch Directives ({data?.recommendations?.length || 0})
            </button>
            <button
              onClick={() => setActiveTab('events')}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition ${
                activeTab === 'events'
                  ? 'bg-slate-800 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Verified City Events ({data?.events_used?.length || 0})
            </button>
            <button
              onClick={() => setActiveTab('table')}
              className={`px-4 py-2 rounded-xl text-sm font-semibold transition ${
                activeTab === 'table'
                  ? 'bg-slate-800 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Hourly Dispatch Table
            </button>
          </div>

          {activeTab === 'events' && (
            <button
              onClick={() => {
                setNewEvent(prev => ({ ...prev, date: selectedDate }));
                setShowAddEventModal(true);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white transition shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Custom Event</span>
            </button>
          )}
        </div>

        {/* Tab 1: AI Dispatch Directives */}
        {activeTab === 'directives' && (
          <div className="space-y-3">
            {(!data?.recommendations || data.recommendations.length === 0) ? (
              <div className="text-center py-10 text-slate-400 text-sm">
                ✅ No schedule adjustments needed. Baseline timetable is optimal for {formatDate(selectedDate)}.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {data.recommendations.map((rec, idx) => {
                  const isCrit = rec.severity === 'critical';
                  const isWarn = rec.severity === 'warning';
                  const border = isCrit ? 'border-rose-500/30 bg-rose-950/15' : isWarn ? 'border-amber-500/30 bg-amber-950/15' : 'border-slate-800 bg-slate-950/40';
                  const badge = isCrit ? 'bg-rose-500/20 text-rose-300' : isWarn ? 'bg-amber-500/20 text-amber-300' : 'bg-slate-800 text-slate-300';
                  
                  return (
                    <div key={idx} className={`p-4 rounded-xl border ${border} space-y-2`}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                          {rec.corridor}
                        </span>
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full font-mono ${badge}`}>
                          {rec.severity}
                        </span>
                      </div>
                      <p className="text-sm text-slate-200 leading-relaxed font-normal">
                        {rec.message}
                      </p>
                      {rec.action && (
                        <p className="text-xs text-cyan-400 font-medium pt-1 border-t border-slate-800/80">
                          ➔ Action: {rec.action}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Verified City Events */}
        {activeTab === 'events' && (
          <div className="space-y-4">
            {(!data?.events_used || data.events_used.length === 0) ? (
              <div className="text-center py-10 text-slate-400 text-sm">
                No major stadium or convention events on {formatDate(selectedDate)}. Standard commuter dispatch active.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {data.events_used.map((ev, idx) => (
                  <div key={ev.id || idx} className="p-4 rounded-xl border border-slate-800 bg-slate-950/40 space-y-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <h4 className="text-sm font-bold text-white">{ev.name}</h4>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {ev.venue_name || 'Hyderabad Venue'} • Nearest Metro: <strong className="text-slate-200">{ev.nearest_station?.stop_name}</strong>
                        </p>
                      </div>
                      <button
                        onClick={() => handleRemoveEvent(ev)}
                        className="px-2.5 py-1 text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded-lg transition border border-rose-500/20"
                        title="Exclude from schedule optimization"
                      >
                        Exclude
                      </button>
                    </div>

                    <div className="flex items-center gap-3 text-xs text-slate-300 pt-1 border-t border-slate-800/80">
                      <span>Attendance: <strong>{ev.expected_attendance?.toLocaleString() || '15,000'}</strong></span>
                      <span>Metro Riders: <strong className="text-cyan-300">+{ev.metro_riders?.toLocaleString()}</strong></span>
                      <span className="text-slate-500 ml-auto font-mono">{formatEventTime(ev.start_time)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Excluded Events Recovery */}
            {data?.events_excluded?.length > 0 && (
              <div className="pt-3 border-t border-slate-800">
                <span className="text-xs font-semibold text-slate-400 block mb-2">Excluded Events:</span>
                <div className="flex flex-wrap gap-2">
                  {data.events_excluded.map((ev, i) => (
                    <span key={i} className="inline-flex items-center gap-2 bg-slate-950/60 border border-slate-800 px-3 py-1 rounded-xl text-xs text-slate-300">
                      <span>{ev.name}</span>
                      <button
                        onClick={() => handleRestoreEvent(ev.id || ev.name)}
                        className="text-cyan-400 hover:underline font-semibold"
                      >
                        Restore
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Hourly Dispatch Table */}
        {activeTab === 'table' && (
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 font-medium">
                <tr>
                  <th className="py-3 px-4">Hour Window</th>
                  <th className="py-3 px-4 text-cyan-400">Inbound ({corridorInfo.inboundRoute})</th>
                  <th className="py-3 px-4 text-rose-400">Outbound ({corridorInfo.outboundRoute})</th>
                  <th className="py-3 px-4 text-slate-400">Baseline GTFS</th>
                  <th className="py-3 px-4 text-slate-400">Flow Split</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {corridorRows.map((r, i) => {
                  const inFrac = Math.round((r.inbound_fraction || 0.5) * 100);
                  const outFrac = Math.round((r.outbound_fraction || 0.5) * 100);
                  return (
                    <tr key={i} className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-4 font-sans font-semibold text-slate-200">
                        {String(r.hour).padStart(2, '0')}:00 - {String(r.hour + 1).padStart(2, '0')}:00
                      </td>
                      <td className="py-2.5 px-4 text-cyan-300 font-bold">
                        {r.inbound_headway}m ({r.inbound_tph} TPH)
                      </td>
                      <td className="py-2.5 px-4 text-rose-300 font-bold">
                        {r.outbound_headway}m ({r.outbound_tph} TPH)
                      </td>
                      <td className="py-2.5 px-4 text-slate-400 font-sans">
                        {r.baseline_headway}m
                      </td>
                      <td className="py-2.5 px-4 font-sans">
                        <span className="text-cyan-400 font-mono">{inFrac}%</span> / <span className="text-rose-400 font-mono">{outFrac}%</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── Add Custom Event Modal ─── */}
      {showAddEventModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl text-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <Calendar className="w-5 h-5 text-cyan-400" />
                Add Custom City Event
              </h3>
              <button
                onClick={() => setShowAddEventModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateEvent} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Event Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Hyderabad Sunrisers vs CSK"
                  value={newEvent.name}
                  onChange={e => setNewEvent({ ...newEvent, name: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Venue Preset</label>
                  <select
                    value={newEvent.venue_key}
                    onChange={e => {
                      const v = VENUE_OPTIONS.find(x => x.key === e.target.value);
                      setNewEvent({
                        ...newEvent,
                        venue_key: e.target.value,
                        nearest_stop_id: v?.nearest_stop_id || 'STD',
                        distance_to_nearest_metro_km: v?.distance_km || 0.7,
                        venue_capacity: v?.capacity || 15000,
                      });
                    }}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  >
                    {VENUE_OPTIONS.map(v => (
                      <option key={v.key} value={v.key}>{v.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Event Type</label>
                  <select
                    value={newEvent.event_type}
                    onChange={e => setNewEvent({ ...newEvent, event_type: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-cyan-500"
                  >
                    <option value="cricket_international">Cricket Match</option>
                    <option value="concert">Live Concert / Music</option>
                    <option value="tech_summit">Tech Summit / Expo</option>
                    <option value="college_fest">College Festival</option>
                    <option value="political_rally">Public Gathering</option>
                    <option value="other">Other Event</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Start Time</label>
                  <input
                    type="time"
                    value={newEvent.start_time}
                    onChange={e => setNewEvent({ ...newEvent, start_time: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-2 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">End Time</label>
                  <input
                    type="time"
                    value={newEvent.end_time}
                    onChange={e => setNewEvent({ ...newEvent, end_time: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-2 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">Attendees</label>
                  <input
                    type="number"
                    value={newEvent.venue_capacity}
                    onChange={e => setNewEvent({ ...newEvent, venue_capacity: parseInt(e.target.value, 10) || 10000 })}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-2.5 py-2 text-xs text-white"
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-slate-800 flex justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setShowAddEventModal(false)}
                  className="px-4 py-2 text-xs rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addEventSubmitting}
                  className="px-4 py-2 text-xs font-semibold rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white transition disabled:opacity-50"
                >
                  {addEventSubmitting ? 'Simulating...' : 'Simulate & Optimize'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
