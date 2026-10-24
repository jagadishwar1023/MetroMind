import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getMetroScheduleLines,
  getMetroDepartures,
  getMetroStationSequence,
  getMetroScheduleEvents,
  createMetroScheduleEvent,
  deleteMetroScheduleEvent,
  resetMetroScheduleEvents,
} from '../api/client';
import {
  Train, Clock, ArrowRightLeft, Calendar, Search, Filter,
  ShieldCheck, AlertTriangle, Info, CheckCircle2, MapPin,
  ChevronRight, RefreshCw, Zap, ArrowRight, ExternalLink,
  Layers, Radio, Compass, CloudRain, Sun, Activity, Warehouse,
  Gauge, Users, ChevronDown, ChevronUp, Cpu, Plus, Trash2, RotateCcw, X
} from 'lucide-react';

const PERIOD_FILTERS = [
  { id: 'all', label: 'All Day', timeRange: '06:00 – 23:36' },
  { id: 'morning_peak', label: 'Morning Peak', timeRange: '08:00 – 11:00', startHour: 8, endHour: 11 },
  { id: 'midday', label: 'Midday Off-Peak', timeRange: '11:00 – 17:00', startHour: 11, endHour: 17 },
  { id: 'evening_peak', label: 'Evening Peak', timeRange: '17:00 – 20:00', startHour: 17, endHour: 20 },
  { id: 'night', label: 'Late Night', timeRange: '20:00 – 23:36', startHour: 20, endHour: 24 },
];

export default function MetroSchedule() {
  // State
  const [lines, setLines] = useState([]);
  const [selectedLine, setSelectedLine] = useState('RED');
  const [selectedTerminal, setSelectedTerminal] = useState('MYP');
  const [selectedDate, setSelectedDate] = useState(() => {
    // Current IST date (YYYY-MM-DD)
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + istOffset);
    return istTime.toISOString().split('T')[0];
  });
  const [scheduleMode, setScheduleMode] = useState('official'); // 'official' | 'estimated'

  // Data
  const [scheduleData, setScheduleData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  // Filters
  const [periodFilter, setPeriodFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showSequence, setShowSequence] = useState(false);
  const [showMathDetails, setShowMathDetails] = useState(false);

  // Real-time IST clock for live countdown updates
  const [currentTimeSecs, setCurrentTimeSecs] = useState(() => {
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + istOffset);
    return istTime.getHours() * 3600 + istTime.getMinutes() * 60 + istTime.getSeconds();
  });

  // Ticking clock every 1 second
  useEffect(() => {
    const timer = setInterval(() => {
      const now = new Date();
      const istOffset = 5.5 * 60 * 60 * 1000;
      const istTime = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + istOffset);
      setCurrentTimeSecs(istTime.getHours() * 3600 + istTime.getMinutes() * 60 + istTime.getSeconds());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch initial lines metadata
  useEffect(() => {
    const fetchLines = async () => {
      try {
        const res = await getMetroScheduleLines();
        if (res?.lines?.length) {
          setLines(res.lines);
        }
      } catch (err) {
        console.error('Failed to load metro lines:', err);
      }
    };
    fetchLines();
  }, []);

  // Active line metadata
  const currentLineInfo = useMemo(() => {
    return lines.find(l => l.id === selectedLine) || {
      id: 'RED',
      name: 'Red Line (Corridor 1)',
      route_color: '#E31E24',
      station_count: 27,
      length_km: 29.2,
      terminals: [
        { stop_id: 'MYP', stop_name: 'Miyapur', destination_id: 'LBN', destination_name: 'L. B. Nagar' },
        { stop_id: 'LBN', stop_name: 'L. B. Nagar', destination_id: 'MYP', destination_name: 'Miyapur' },
      ],
    };
  }, [lines, selectedLine]);

  // Fetch departures for current line, terminal, and date
  const fetchDepartures = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      setError(null);

      const params = {
        line: selectedLine,
        terminal: selectedTerminal,
        target_date: selectedDate,
        mode: scheduleMode,
      };

      const res = await getMetroDepartures(params);
      setScheduleData(res);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load timetable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedLine, selectedTerminal, selectedDate, scheduleMode]);

  useEffect(() => {
    fetchDepartures();
  }, [fetchDepartures]);

  // Event Management State & Handlers
  const [scheduleEvents, setScheduleEvents] = useState([]);
  const [availableVenues, setAvailableVenues] = useState([]);
  const [showEventModal, setShowEventModal] = useState(false);
  const [eventFeedback, setEventFeedback] = useState(null);
  const [eventLoading, setEventLoading] = useState(false);
  const [newEvent, setNewEvent] = useState({
    name: '',
    corridor: 'BLUE',
    venue_id: 'uppal_stadium',
    start_time: '19:00',
    end_time: '22:30',
    expected_attendance: 35000,
    metro_riders: 5250,
    event_type: 'cricket_ipl',
  });

  const fetchEvents = useCallback(async () => {
    try {
      const data = await getMetroScheduleEvents(selectedDate);
      setScheduleEvents(data.events || []);
      if (data.available_venues?.length) {
        setAvailableVenues(data.available_venues);
      }
    } catch (e) {
      console.error('Failed to load schedule events:', e);
    }
  }, [selectedDate]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const handleAddEvent = async (e) => {
    if (e) e.preventDefault();
    if (!newEvent.name.trim()) return;
    setEventLoading(true);
    try {
      const venueObj = availableVenues.find(v => v.id === newEvent.venue_id);
      await createMetroScheduleEvent({
        ...newEvent,
        date: selectedDate,
        corridor: venueObj?.corridor || newEvent.corridor,
        venue_name: venueObj?.name,
        nearest_stop_id: venueObj?.nearest_stop_id,
      });
      setShowEventModal(false);
      const evName = newEvent.name;
      setNewEvent({
        name: '',
        corridor: 'BLUE',
        venue_id: availableVenues[0]?.id || 'uppal_stadium',
        start_time: '19:00',
        end_time: '22:30',
        expected_attendance: 35000,
        metro_riders: 5250,
        event_type: 'cricket_ipl',
      });
      setEventFeedback({ type: 'success', message: `Event "${evName}" added! Headway compressed during event window.` });
      setTimeout(() => setEventFeedback(null), 5000);
      await Promise.all([fetchEvents(), fetchDepartures()]);
    } catch (err) {
      setEventFeedback({ type: 'error', message: err?.response?.data?.detail || err?.message || 'Failed to add event.' });
    } finally {
      setEventLoading(false);
    }
  };

  const handleRemoveEvent = async (eventId, eventName) => {
    setEventLoading(true);
    try {
      await deleteMetroScheduleEvent(eventId);
      setEventFeedback({ type: 'info', message: `Event "${eventName}" removed! Headway relaxed back to baseline.` });
      setTimeout(() => setEventFeedback(null), 5000);
      await Promise.all([fetchEvents(), fetchDepartures()]);
    } catch (err) {
      setEventFeedback({ type: 'error', message: err?.response?.data?.detail || err?.message || 'Failed to remove event.' });
    } finally {
      setEventLoading(false);
    }
  };

  const handleResetEvents = async () => {
    setEventLoading(true);
    try {
      await resetMetroScheduleEvents();
      setEventFeedback({ type: 'success', message: 'Restored all verified city events.' });
      setTimeout(() => setEventFeedback(null), 5000);
      await Promise.all([fetchEvents(), fetchDepartures()]);
    } catch (err) {
      setEventFeedback({ type: 'error', message: 'Failed to restore events.' });
    } finally {
      setEventLoading(false);
    }
  };

  // Handle switching metro line
  const handleLineChange = (lineId) => {
    if (lineId === selectedLine) return;
    setSelectedLine(lineId);
    const lineObj = lines.find(l => l.id === lineId);
    if (lineObj?.terminals?.length) {
      setSelectedTerminal(lineObj.terminals[0].stop_id);
    }
  };

  // Handle swapping terminal direction
  const handleSwapDirection = () => {
    if (!currentLineInfo?.terminals || currentLineInfo.terminals.length < 2) return;
    const otherTerm = currentLineInfo.terminals.find(t => t.stop_id !== selectedTerminal);
    if (otherTerm) {
      setSelectedTerminal(otherTerm.stop_id);
    }
  };

  // Live upcoming departures calculation based on ticking seconds
  const liveNextDepartures = useMemo(() => {
    if (!scheduleData?.all_departures?.length) return [];
    const all = scheduleData.all_departures;

    // Filter departures whose departure_seconds >= currentTimeSecs
    const upcoming = all.filter(d => d.departure_seconds >= currentTimeSecs).slice(0, 5);

    if (upcoming.length === 0) {
      // Outside operational hours (post last train)
      return [];
    }

    return upcoming.map((dep) => {
      const remainingSecs = Math.max(0, dep.departure_seconds - currentTimeSecs);
      const mins = Math.floor(remainingSecs / 60);
      const secs = remainingSecs % 60;
      let countdown = '';
      let isBoarding = false;

      if (remainingSecs <= 45) {
        countdown = 'Boarding Now';
        isBoarding = true;
      } else if (mins < 60) {
        countdown = `In ${mins}m ${secs.toString().padStart(2, '0')}s`;
      } else {
        const hrs = Math.floor(mins / 60);
        const remMins = mins % 60;
        countdown = `In ${hrs}h ${remMins}m`;
      }

      return {
        ...dep,
        secondsRemaining: remainingSecs,
        countdownDisplay: countdown,
        isBoarding,
      };
    });
  }, [scheduleData, currentTimeSecs]);

  // Full day filtered departures
  const filteredAllDepartures = useMemo(() => {
    if (!scheduleData?.all_departures) return [];
    let list = scheduleData.all_departures;

    // Period Filter
    if (periodFilter !== 'all') {
      const pf = PERIOD_FILTERS.find(p => p.id === periodFilter);
      if (pf && pf.startHour !== undefined && pf.endHour !== undefined) {
        list = list.filter(d => {
          const hour = Math.floor(d.departure_seconds / 3600);
          return hour >= pf.startHour && hour < pf.endHour;
        });
      }
    }

    // Search query filter (e.g. "08:", "06:30", "18")
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter(d =>
        d.departure_time.toLowerCase().includes(q) ||
        d.departure_time_12h.toLowerCase().includes(q) ||
        (d.trip_id && d.trip_id.toLowerCase().includes(q))
      );
    }

    return list;
  }, [scheduleData, periodFilter, searchQuery]);

  const summary = scheduleData?.summary || {};
  const classification = scheduleData?.data_classification || {};
  const liveStatus = scheduleData?.live_status || {};
  const serviceNotice = scheduleData?.service_notice;
  const isOperatingHours = summary.is_operating_hours;
  const sequence = scheduleData?.station_sequence || [];
  const fleetTelemetry = scheduleData?.fleet_telemetry;

  return (
    <div className="space-y-6 animate-fade-in pb-16">
      {/* ─── Top Page Header ─── */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-slate-900/60 p-5 rounded-2xl border border-slate-800 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-cyan-500/10 text-cyan-400 rounded-xl border border-cyan-500/20 shadow-inner">
            <Train className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl md:text-2xl font-black text-white tracking-tight">
                Metro Train Schedule
              </h1>
              <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono font-semibold">
                HMRL GTFS v2.4
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Verified terminal departure timings, live departure countdowns, and operational timetables for Hyderabad Metro.
            </p>
          </div>
        </div>

        {/* Live IST Clock & Mode Toggle */}
        <div className="flex flex-wrap items-center gap-3 self-end lg:self-center">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-950/80 border border-slate-800 text-xs text-slate-300 font-mono">
            <Clock className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
            <span className="text-slate-400 text-[11px]">IST:</span>
            <span className="font-bold text-white">
              {Math.floor(currentTimeSecs / 3600).toString().padStart(2, '0')}:
              {Math.floor((currentTimeSecs % 3600) / 60).toString().padStart(2, '0')}:
              {(currentTimeSecs % 60).toString().padStart(2, '0')}
            </span>
          </div>

          <div className="flex bg-slate-950/80 p-1 rounded-xl border border-slate-800 text-xs">
            <button
              onClick={() => setScheduleMode('official')}
              className={`px-3 py-1 rounded-lg font-medium transition ${
                scheduleMode === 'official'
                  ? 'bg-cyan-600 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Official GTFS
            </button>
            <button
              onClick={() => setScheduleMode('estimated')}
              className={`px-3 py-1 rounded-lg font-medium transition ${
                scheduleMode === 'estimated'
                  ? 'bg-amber-600 text-white font-bold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Estimated Mode
            </button>
          </div>

          <button
            onClick={() => fetchDepartures(true)}
            disabled={refreshing || loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-cyan-400' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ─── Line Selector Tabs ─── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {[
          {
            id: 'RED',
            name: 'Red Line (Corridor 1)',
            route: 'Miyapur ⇄ L.B. Nagar',
            color: '#E31E24',
            bgGlow: 'hover:border-rose-500/50',
            activeClass: 'border-rose-500 bg-rose-500/10 text-rose-200 shadow-rose-950/30',
            activeDot: 'bg-rose-500',
            stations: 27,
            length: '29.2 km',
          },
          {
            id: 'BLUE',
            name: 'Blue Line (Corridor 3)',
            route: 'Nagole ⇄ Raidurg',
            color: '#007ABB',
            bgGlow: 'hover:border-blue-500/50',
            activeClass: 'border-blue-500 bg-blue-500/10 text-blue-200 shadow-blue-950/30',
            activeDot: 'bg-blue-500',
            stations: 23,
            length: '27.0 km',
          },
          {
            id: 'GREEN',
            name: 'Green Line (Corridor 2)',
            route: 'JBS Parade Ground ⇄ MGBS',
            color: '#009846',
            bgGlow: 'hover:border-emerald-500/50',
            activeClass: 'border-emerald-500 bg-emerald-500/10 text-emerald-200 shadow-emerald-950/30',
            activeDot: 'bg-emerald-500',
            stations: 9,
            length: '11.0 km',
          },
        ].map((line) => {
          const isActive = selectedLine === line.id;
          return (
            <button
              key={line.id}
              onClick={() => handleLineChange(line.id)}
              className={`p-4 rounded-2xl border text-left transition flex flex-col justify-between shadow-md ${
                isActive
                  ? `${line.activeClass} shadow-lg`
                  : `bg-slate-900/70 border-slate-800 text-slate-300 ${line.bgGlow}`
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold tracking-wider uppercase font-mono flex items-center gap-1.5">
                  <span className={`w-2.5 h-2.5 rounded-full ${isActive ? line.activeDot : 'bg-slate-600'}`} />
                  {line.name}
                </span>
                <span className="text-[11px] text-slate-400 font-mono">
                  {line.stations} Stns • {line.length}
                </span>
              </div>
              <div className="mt-2 text-sm font-bold text-white flex items-center justify-between">
                <span>{line.route}</span>
                <ChevronRight className={`w-4 h-4 transition ${isActive ? 'translate-x-1 text-white' : 'text-slate-600'}`} />
              </div>
            </button>
          );
        })}
      </div>

      {/* ─── Terminal Origin / Destination & Swap Toolbar ─── */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 md:p-5 shadow-sm space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-400 flex items-center gap-1 mr-1">
              <MapPin className="w-3.5 h-3.5 text-cyan-400" /> Origin Terminal:
            </span>

            {currentLineInfo.terminals?.map((t) => {
              const isSelected = selectedTerminal === t.stop_id;
              return (
                <button
                  key={t.stop_id}
                  onClick={() => setSelectedTerminal(t.stop_id)}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border ${
                    isSelected
                      ? 'bg-cyan-500/20 text-cyan-200 border-cyan-500/60 shadow-sm shadow-cyan-900/40'
                      : 'bg-slate-800/60 text-slate-400 border-slate-700/60 hover:bg-slate-800 hover:text-slate-200'
                  }`}
                >
                  <Train className="w-3.5 h-3.5" />
                  {t.stop_name}
                  <span className="text-[10px] text-slate-400 font-mono">({t.platform})</span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2 self-start md:self-auto">
            <button
              onClick={handleSwapDirection}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 text-xs font-bold border border-slate-700 transition shadow-sm"
              title="Reverse terminal travel direction"
            >
              <ArrowRightLeft className="w-3.5 h-3.5 text-cyan-400" />
              Switch Direction
            </button>

            <button
              onClick={() => setShowSequence(!showSequence)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-slate-800/70 hover:bg-slate-800 text-slate-300 text-xs font-medium border border-slate-700/70 transition"
            >
              <Layers className="w-3.5 h-3.5 text-slate-400" />
              {showSequence ? 'Hide Route' : `View ${sequence.length || currentLineInfo.station_count} Stations`}
            </button>
          </div>
        </div>

        {/* Current Active Trip Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-slate-200">
            <span className="font-bold text-white flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              Departing From:
            </span>
            <span className="font-black text-cyan-300 text-sm">{summary.origin_name}</span>
            <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-slate-400">Destination:</span>
            <span className="font-bold text-white text-sm">{summary.destination_name}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-400 font-mono">
            <span>Operating Hours:</span>
            <span className="text-white font-bold bg-slate-800/80 px-2 py-0.5 rounded border border-slate-700">
              {summary.first_train_departure} – {summary.last_train_departure}
            </span>
            <span>•</span>
            <span>Peak Headway:</span>
            <span className="text-cyan-300 font-bold">~{summary.peak_frequency_min}m</span>
          </div>
        </div>

        {/* Station Sequence Accordion */}
        {showSequence && (
          <div className="pt-3 border-t border-slate-800 animate-fade-in">
            <div className="text-xs text-slate-400 mb-2 font-semibold flex items-center justify-between">
              <span>Station Sequence in Travel Direction ({summary.origin_name} ➔ {summary.destination_name})</span>
              <span className="text-[10px] text-slate-500 font-mono">Total {sequence.length} Stations</span>
            </div>
            <div className="flex flex-wrap gap-1.5 p-3 bg-slate-950/70 border border-slate-800 rounded-xl max-h-48 overflow-y-auto">
              {sequence.map((st, idx) => {
                const isTerm = idx === 0 || idx === sequence.length - 1;
                return (
                  <div
                    key={st.stop_id + idx}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] border ${
                      isTerm
                        ? 'bg-cyan-500/20 text-cyan-200 border-cyan-500/40 font-bold'
                        : st.is_interchange
                        ? 'bg-amber-500/15 text-amber-200 border-amber-500/30 font-semibold'
                        : 'bg-slate-900 text-slate-300 border-slate-800'
                    }`}
                  >
                    <span className="text-[9px] font-mono opacity-60">{st.sequence_number}.</span>
                    <span>{st.stop_name}</span>
                    {st.is_interchange && (
                      <span className="text-[9px] px-1 bg-amber-400/20 text-amber-300 rounded font-mono font-bold">
                        Interchange ({st.interchange_corridors.join('/')})
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ─── Fleet Telemetry & Dynamic Demand Cockpit ─── */}
      {fleetTelemetry && (
        <div className={`p-5 md:p-6 rounded-2xl border shadow-lg space-y-4 transition ${
          scheduleMode === 'estimated'
            ? 'bg-gradient-to-br from-amber-950/20 via-slate-900/90 to-slate-900 border-amber-500/30'
            : 'bg-slate-900/80 border-slate-800'
        }`}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3.5">
            <div className="flex items-center gap-2.5">
              <div className={`p-2 rounded-xl border ${
                scheduleMode === 'estimated'
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  : 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
              }`}>
                <Cpu className="w-5 h-5 animate-pulse" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base md:text-lg font-black text-white tracking-tight">
                    57-Train Fleet Telemetry & Depot Stabling
                  </h2>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold border ${
                    scheduleMode === 'estimated'
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                      : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                  }`}>
                    {scheduleMode === 'estimated' ? 'DYNAMIC ML ESTIMATION' : 'BASELINE FLEET CONTEXT'}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  {fleetTelemetry.stabling_status_note}
                </p>
              </div>
            </div>

            <button
              onClick={() => setShowMathDetails(!showMathDetails)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-800 text-slate-300 text-xs font-semibold border border-slate-700 transition self-start sm:self-auto"
            >
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <span>{showMathDetails ? 'Hide Equations' : 'Fleet Math & Equations'}</span>
              {showMathDetails ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          </div>

          {/* Key Metrics Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {/* 1. Active Fleet */}
            <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center gap-1 font-semibold">
                  <Train className="w-3.5 h-3.5 text-cyan-400" /> Active Trains
                </span>
                <span className="text-[10px] font-mono text-cyan-300 font-bold">
                  {Math.round((fleetTelemetry.active_trains_total / 57) * 100)}%
                </span>
              </div>
              <div className="mt-2 text-xl font-black text-white font-mono flex items-baseline gap-1.5">
                <span>{fleetTelemetry.active_trains_total}</span>
                <span className="text-xs text-slate-500 font-normal">/ 57 Trains</span>
              </div>
              <div className="mt-1 text-[11px] text-slate-400 flex items-center justify-between">
                <span>{fleetTelemetry.corridor_active_trains} on {currentLineInfo.name.split(' ')[0]} Line</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-300 font-mono">Mainline</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2.5 overflow-hidden">
                <div
                  className="bg-cyan-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${(fleetTelemetry.active_trains_total / 57) * 100}%` }}
                />
              </div>
            </div>

            {/* 2. Stationed at Depots (Low Crowd Buffer) */}
            <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center gap-1 font-semibold">
                  <Warehouse className="w-3.5 h-3.5 text-amber-400" /> Stationed at Depots
                </span>
                <span className="text-[10px] font-mono text-amber-300 font-bold">
                  {Math.round((fleetTelemetry.stationed_trains_total / 57) * 100)}%
                </span>
              </div>
              <div className="mt-2 text-xl font-black text-amber-300 font-mono flex items-baseline gap-1.5">
                <span>{fleetTelemetry.stationed_trains_total}</span>
                <span className="text-xs text-slate-500 font-normal">/ 57 Trains</span>
              </div>
              <div className="mt-1 text-[11px] text-slate-400 flex items-center justify-between">
                <span>{fleetTelemetry.current_hour >= 22 ? 'Night Stabling (5-15)' : 'Day Stabling (2-4)'}</span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-300 font-mono">Standby</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2.5 overflow-hidden">
                <div
                  className="bg-amber-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${(fleetTelemetry.stationed_trains_total / 57) * 100}%` }}
                />
              </div>
            </div>

            {/* 3. Weather Demand Multiplier */}
            <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center gap-1 font-semibold">
                  {fleetTelemetry.weather_impact?.is_rain ? (
                    <CloudRain className="w-3.5 h-3.5 text-blue-400 animate-bounce" />
                  ) : (
                    <Sun className="w-3.5 h-3.5 text-amber-400" />
                  )}
                  Weather Factor
                </span>
                <span className="text-[10px] font-mono text-slate-400">
                  {fleetTelemetry.weather_impact?.precipitation_mm || 0}mm rain
                </span>
              </div>
              <div className="mt-2 text-xl font-black text-white font-mono flex items-baseline gap-1.5">
                <span>{fleetTelemetry.weather_impact?.multiplier || 1.0}x</span>
                <span className="text-xs text-slate-400 font-normal">modal shift</span>
              </div>
              <div className="mt-1 text-[11px] text-slate-400 truncate" title={fleetTelemetry.weather_impact?.description}>
                {fleetTelemetry.weather_impact?.description || 'Clear & Normal Commute'}
              </div>
              <div className="mt-2 text-[10px] text-slate-500 font-mono">
                {fleetTelemetry.weather_impact?.is_rain ? 'Wet roads shift commuters to metro' : 'Dry conditions, normal load'}
              </div>
            </div>

            {/* 4. Live City Events & Headway */}
            <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center gap-1 font-semibold">
                  <Users className="w-3.5 h-3.5 text-emerald-400" /> Event Surge
                </span>
                <span className="text-[10px] font-mono text-emerald-300 font-bold">
                  {fleetTelemetry.events_impact?.events_count || 0} Events
                </span>
              </div>
              <div className="mt-2 text-xl font-black text-emerald-300 font-mono flex items-baseline gap-1.5">
                <span>+{fleetTelemetry.events_impact?.corridor_surge_pax?.toLocaleString() || 0}</span>
                <span className="text-xs text-slate-500 font-normal">pax/hr</span>
              </div>
              <div className="mt-1 text-[11px] text-slate-400 flex items-center justify-between">
                <span>Effective Headway:</span>
                <span className="text-white font-bold font-mono">~{fleetTelemetry.current_headway_min}m</span>
              </div>
              <div className="mt-2 text-[10px] text-slate-500 font-mono truncate">
                {fleetTelemetry.events_impact?.active_events?.length > 0
                  ? fleetTelemetry.events_impact.active_events[0].name
                  : 'Standard baseline commuter flow'}
              </div>
            </div>
          </div>

          {/* Stabling Depots Breakdown Bar */}
          <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800/80 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                <Warehouse className="w-3.5 h-3.5 text-amber-400" />
                Active Depot Stabling Breakdown:
              </span>
              <span className="text-[11px] text-slate-400 font-mono">
                57 Total = {fleetTelemetry.active_trains_total} Mainline + {fleetTelemetry.stationed_trains_total} Stabled + 3 Reserve
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 pt-1 text-xs font-mono">
              <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-slate-400 block font-sans">Miyapur Depot (Red)</span>
                  <span className="font-bold text-rose-300">{fleetTelemetry.depots?.miyapur?.stabled || 0} Stabled</span>
                </div>
                <span className="text-[10px] text-slate-500">Cap: 28</span>
              </div>

              <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-slate-400 block font-sans">Uppal Depot (Blue)</span>
                  <span className="font-bold text-blue-300">{fleetTelemetry.depots?.uppal?.stabled || 0} Stabled</span>
                </div>
                <span className="text-[10px] text-slate-500">Cap: 24</span>
              </div>

              <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-slate-400 block font-sans">MGBS Sidings (Green)</span>
                  <span className="font-bold text-emerald-300">{fleetTelemetry.depots?.mgbs?.stabled || 0} Stabled</span>
                </div>
                <span className="text-[10px] text-slate-500">Cap: 6</span>
              </div>

              <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-slate-400 block font-sans">Maintenance Yard</span>
                  <span className="font-bold text-slate-300">{fleetTelemetry.reserve_maintenance || 3} Reserve</span>
                </div>
                <span className="text-[10px] text-slate-500">Rolling Spare</span>
              </div>
            </div>
          </div>

          {/* Mathematical Formulation Drawer */}
          {showMathDetails && (
            <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-3 animate-fade-in text-xs">
              <div className="flex items-center gap-2 text-cyan-400 font-bold border-b border-slate-800 pb-2">
                <Gauge className="w-4 h-4" />
                Mathematical Formulation & Fleet Optimization Model
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-slate-300">
                <div className="space-y-1.5 p-3 rounded-lg bg-slate-900/60 border border-slate-800/60 font-mono text-[11px]">
                  <div className="text-cyan-300 font-bold font-sans">1. Transit Engineering Frequency & Headway Equation:</div>
                  <p className="text-slate-300 font-semibold">
                    TPH_target = (60 / H_base) × W_mult + (E_pax / 250)
                  </p>
                  <p className="text-slate-300 font-semibold">
                    H_effective = clamp(60 / TPH_target, 2.5m, 15.0m)
                  </p>
                  <p className="text-slate-500 text-[10px] font-sans">
                    Where H_base is HMRL's published baseline headway (4.0m peak, 6.5m midday off-peak, 9.0–11.0m night), W_mult is rain modal shift, and E_pax / 250 injects extra hourly train throughput to absorb stadium & venue crowds.
                  </p>
                </div>

                <div className="space-y-1.5 p-3 rounded-lg bg-slate-900/60 border border-slate-800/60 font-mono text-[11px]">
                  <div className="text-amber-300 font-bold font-sans">2. 57-Train Fleet Ceiling & Stabling Constraints:</div>
                  <p className="text-slate-300 font-semibold">
                    Daytime (07:00–22:00): 53–55 active (only 2–4 stabled)
                  </p>
                  <p className="text-slate-300 font-semibold">
                    Night (after 10 PM): 5–15 stabled based on crowd demand
                  </p>
                  <p className="text-slate-500 text-[10px] font-sans">
                    Active operational trains include mainline consists rolling on Red (RTT 72m), Blue (RTT 66m), and Green (RTT 26m) plus terminal turnback hot-standbys. Stabled consists are stationed across Miyapur, Uppal, and MGBS depots.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ─── City Events & Transit Crowd Manager ─── */}
      <div className="p-5 md:p-6 rounded-2xl border border-slate-800 bg-slate-900/80 shadow-md space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3.5">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base md:text-lg font-black text-white tracking-tight">
                  City Events & Transit Demand Manager
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-mono font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  {scheduleEvents.length} ACTIVE ON {selectedDate}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Add or remove events to dynamically simulate crowd surges and observe real-time headway compression across corridors.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowEventModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 text-xs font-semibold border border-emerald-500/40 transition shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Event</span>
            </button>

            <button
              onClick={handleResetEvents}
              disabled={eventLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-slate-800 text-slate-300 text-xs font-semibold border border-slate-700 transition"
              title="Restore all default scraped events"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              <span>Reset</span>
            </button>
          </div>
        </div>

        {/* Feedback message banner */}
        {eventFeedback && (
          <div className={`p-3 rounded-xl text-xs font-medium border flex items-center justify-between animate-fade-in ${
            eventFeedback.type === 'error'
              ? 'bg-rose-500/15 border-rose-500/30 text-rose-300'
              : 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
          }`}>
            <span className="flex items-center gap-2">
              <Zap className="w-3.5 h-3.5" />
              {eventFeedback.message}
            </span>
            <button onClick={() => setEventFeedback(null)} className="text-slate-400 hover:text-white">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Events Cards Grid */}
        {scheduleEvents.length === 0 ? (
          <div className="p-6 bg-slate-950/60 rounded-xl border border-dashed border-slate-800 text-center space-y-2">
            <p className="text-xs text-slate-400">
              No events scheduled for this date. The metro is operating on its standard continuous commuter baseline.
            </p>
            <button
              onClick={() => setShowEventModal(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-300 text-xs font-semibold border border-emerald-500/30 hover:bg-emerald-500/25 transition"
            >
              <Plus className="w-3.5 h-3.5" /> Add an event (e.g. Cricket Match / Concert) to simulate crowd surge
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {scheduleEvents.map((ev) => {
              const cor = ev.nearest_station?.corridors?.[0] || ev.corridor || 'BLUE';
              const corColor = cor === 'RED' ? 'border-rose-500/40 text-rose-300 bg-rose-500/10' : (cor === 'BLUE' ? 'border-blue-500/40 text-blue-300 bg-blue-500/10' : 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10');
              const sTime = ev.start_time ? (ev.start_time.includes('T') ? ev.start_time.split('T')[1].slice(0, 5) : ev.start_time.slice(0, 5)) : '19:00';
              const eTime = ev.end_time ? (ev.end_time.includes('T') ? ev.end_time.split('T')[1].slice(0, 5) : ev.end_time.slice(0, 5)) : '22:30';

              return (
                <div
                  key={ev.id || ev.name}
                  className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 hover:border-slate-700 flex flex-col justify-between transition space-y-3"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className={`text-[10px] px-2 py-0.5 rounded-md font-mono font-bold uppercase border ${corColor}`}>
                        {cor} LINE
                      </span>
                      <button
                        onClick={() => handleRemoveEvent(ev.id || ev.name, ev.name)}
                        disabled={eventLoading}
                        className="text-slate-500 hover:text-rose-400 p-1 rounded hover:bg-rose-500/10 transition"
                        title="Remove this event from schedule"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <h4 className="text-xs font-bold text-white line-clamp-2" title={ev.name}>
                      {ev.name}
                    </h4>

                    <div className="text-[11px] text-slate-400 flex items-center gap-1 truncate" title={ev.venue_name}>
                      <MapPin className="w-3 h-3 text-slate-500 flex-shrink-0" />
                      <span className="truncate">{ev.venue_name}</span>
                    </div>

                    <div className="text-[11px] text-slate-400 font-mono flex items-center justify-between pt-1 border-t border-slate-800/80">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3 text-cyan-400" />
                        {sTime} – {eTime}
                      </span>
                      <span className="text-emerald-400 font-bold">
                        +{ev.metro_riders || 0} pax
                      </span>
                    </div>
                  </div>

                  <div className="text-[10px] text-slate-500 font-mono flex items-center justify-between">
                    <span>{ev.is_manual ? 'Manual Custom' : 'Verified Scraped'}</span>
                    <span className="text-cyan-400 font-semibold">⚡ Compresses Headway</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Modal for Adding New Event */}
        {showEventModal && (
          <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl space-y-4 animate-fade-in">
              <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                <div className="flex items-center gap-2 text-white font-bold text-base">
                  <Plus className="w-4 h-4 text-emerald-400" />
                  Add Event to Schedule
                </div>
                <button
                  onClick={() => setShowEventModal(false)}
                  className="text-slate-400 hover:text-white transition"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <form onSubmit={handleAddEvent} className="space-y-3.5 text-xs">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Event Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. IPL: SRH vs CSK, Arijit Singh Concert, Tech Summit"
                    value={newEvent.name}
                    onChange={(e) => setNewEvent({ ...newEvent, name: e.target.value })}
                    className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Venue / Station Preset</label>
                    <select
                      value={newEvent.venue_id}
                      onChange={(e) => {
                        const vId = e.target.value;
                        const vObj = availableVenues.find(v => v.id === vId);
                        setNewEvent({
                          ...newEvent,
                          venue_id: vId,
                          corridor: vObj?.corridor || newEvent.corridor,
                          expected_attendance: vObj?.capacity || 20000,
                          metro_riders: Math.round((vObj?.capacity || 20000) * 0.15),
                        });
                      }}
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-cyan-500"
                    >
                      {availableVenues.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name} ({v.corridor} Line)
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Metro Corridor</label>
                    <select
                      value={newEvent.corridor}
                      onChange={(e) => setNewEvent({ ...newEvent, corridor: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-cyan-500"
                    >
                      <option value="BLUE">Blue Line (Nagole ⇄ Raidurg)</option>
                      <option value="RED">Red Line (Miyapur ⇄ LB Nagar)</option>
                      <option value="GREEN">Green Line (JBS ⇄ MGBS)</option>
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Start Time (IST)</label>
                    <input
                      type="time"
                      value={newEvent.start_time}
                      onChange={(e) => setNewEvent({ ...newEvent, start_time: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-slate-300 font-medium mb-1">End Time (IST)</label>
                    <input
                      type="time"
                      value={newEvent.end_time}
                      onChange={(e) => setNewEvent({ ...newEvent, end_time: e.target.value })}
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Total Attendance</label>
                    <input
                      type="number"
                      min="100"
                      step="500"
                      value={newEvent.expected_attendance}
                      onChange={(e) => {
                        const att = parseInt(e.target.value) || 0;
                        setNewEvent({
                          ...newEvent,
                          expected_attendance: att,
                          metro_riders: Math.round(att * 0.15),
                        });
                      }}
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-white focus:outline-none focus:border-cyan-500 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-slate-300 font-medium mb-1">Metro Riders (+Surge)</label>
                    <input
                      type="number"
                      min="50"
                      step="100"
                      value={newEvent.metro_riders}
                      onChange={(e) => setNewEvent({ ...newEvent, metro_riders: parseInt(e.target.value) || 0 })}
                      className="w-full px-3 py-2 rounded-xl bg-slate-950 border border-slate-700 text-emerald-300 focus:outline-none focus:border-cyan-500 font-mono font-bold"
                    />
                  </div>
                </div>

                <div className="pt-3 border-t border-slate-800 flex items-center justify-end gap-2.5">
                  <button
                    type="button"
                    onClick={() => setShowEventModal(false)}
                    className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition"
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={eventLoading}
                    className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold transition flex items-center gap-1.5 shadow-lg shadow-emerald-500/20"
                  >
                    {eventLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                    <span>Add to Schedule</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>

      {/* ─── HERO SECTION: Next Five Departures Panel ─── */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 md:p-6 shadow-xl space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3.5">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-rose-500/10 text-rose-400 rounded-xl border border-rose-500/20">
              <Zap className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h2 className="text-lg md:text-xl font-black text-white flex items-center gap-2">
                Next 5 Departures
                <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono font-bold">
                  LIVE COUNTDOWN
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Next upcoming trains from <span className="text-white font-semibold">{summary.origin_name}</span> ({summary.platform}) towards <span className="text-cyan-300 font-semibold">{summary.destination_name}</span>.
              </p>
            </div>
          </div>

          {/* Classification Badge */}
          <div className="flex items-center gap-2 self-start sm:self-auto">
            {scheduleMode === 'official' ? (
              <span className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 text-xs font-semibold">
                <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
                Official Scheduled
              </span>
            ) : (
              <span className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-amber-500/15 text-amber-300 border border-amber-500/30 text-xs font-semibold">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                Estimated — Not official
              </span>
            )}
          </div>
        </div>

        {/* Departures Grid or Closed Notice */}
        {loading ? (
          <div className="py-12 text-center text-slate-400 flex flex-col items-center justify-center gap-3">
            <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
            <p className="text-sm font-medium">Calculating next departures from GTFS timetable...</p>
          </div>
        ) : liveNextDepartures.length === 0 ? (
          // Outside operational hours (Night / Pre-service)
          <div className="p-6 bg-slate-950/80 rounded-2xl border border-slate-800 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-400 flex items-center justify-center mx-auto">
              <Clock className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white">
                {serviceNotice?.title || 'Service Closed for Today'}
              </h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto mt-1 leading-relaxed">
                {serviceNotice?.message || `All train departures from ${summary.origin_name} have completed for today. Service resumes tomorrow at 06:00:00 AM.`}
              </p>
            </div>
            {serviceNotice?.resumes_in_formatted && (
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-slate-800/80 text-amber-300 text-xs font-mono font-bold border border-slate-700">
                <span>Next First Train:</span>
                <span className="text-white">{serviceNotice.next_first_train}</span>
                <span>• Resumes in {serviceNotice.resumes_in_formatted}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {liveNextDepartures.map((dep, index) => {
              const isFirst = index === 0;
              return (
                <div
                  key={dep.trip_id || dep.departure_time + index}
                  className={`p-4 rounded-2xl border flex flex-col justify-between transition shadow-sm ${
                    isFirst
                      ? 'bg-gradient-to-b from-cyan-950/40 to-slate-900 border-cyan-500/50 shadow-md shadow-cyan-950/50 ring-1 ring-cyan-500/30'
                      : 'bg-slate-950/60 border-slate-800/90 hover:border-slate-700'
                  }`}
                >
                  <div>
                    {/* Position Label & Headway */}
                    <div className="flex items-center justify-between text-xs mb-2">
                      <span className={`text-[10px] px-2 py-0.5 rounded-md font-bold uppercase font-mono ${
                        isFirst
                          ? 'bg-cyan-500 text-slate-950'
                          : 'bg-slate-800 text-slate-400'
                      }`}>
                        {isFirst ? 'Next Train' : `Train #${index + 1}`}
                      </span>

                      {dep.is_event_compressed && dep.headway_compression_min > 0 ? (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono font-bold flex items-center gap-0.5" title={`Compressed by -${dep.headway_compression_min}m from ${dep.base_headway_min}m base`}>
                          <Zap className="w-2.5 h-2.5 text-emerald-400 animate-pulse" />
                          -{dep.headway_compression_min}m Surge
                        </span>
                      ) : dep.headway_min ? (
                        <span className="text-[10px] text-slate-400 font-mono">
                          +{dep.headway_min}m
                        </span>
                      ) : null}
                    </div>

                    {/* Scheduled Departure Time */}
                    <div className="text-xl md:text-2xl font-black text-white font-mono tracking-tight">
                      {dep.departure_time_12h}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">
                      {dep.departure_time} IST
                    </div>

                    {/* Destination & Platform */}
                    <div className="mt-3 text-xs text-slate-300 space-y-1">
                      <div className="flex items-center gap-1 truncate font-medium">
                        <span className="text-slate-400">To:</span>
                        <span className="text-cyan-300 font-semibold truncate">{dep.destination_name}</span>
                      </div>
                      <div className="text-[11px] text-slate-400 flex items-center justify-between">
                        <span>{dep.platform}</span>
                        {dep.active_trains_corridor && (
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800/80 text-cyan-300 font-mono font-semibold">
                            {dep.active_trains_corridor} Active
                          </span>
                        )}
                      </div>
                      {dep.stabled_at_depot !== undefined && (
                        <div className="text-[10px] text-slate-500 font-mono flex items-center justify-between pt-0.5">
                          <span>Stabled:</span>
                          <span className="text-amber-400 font-semibold">
                            {dep.stabled_at_depot} at Depot
                          </span>
                        </div>
                      )}
                      {dep.is_event_compressed && dep.event_name && (
                        <div className="text-[10px] text-emerald-400 font-mono flex items-center gap-1 pt-1 truncate" title={`${dep.event_name} (${dep.event_phase})`}>
                          <Users className="w-3 h-3 flex-shrink-0 text-emerald-400" />
                          <span className="truncate">{dep.event_name}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Live Countdown Footer */}
                  <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between">
                    <span className={`text-xs font-mono font-bold flex items-center gap-1 ${
                      dep.isBoarding
                        ? 'text-amber-400 animate-pulse font-black'
                        : isFirst
                        ? 'text-cyan-300 font-black'
                        : 'text-slate-300'
                    }`}>
                      <Clock className="w-3.5 h-3.5" />
                      {dep.countdownDisplay}
                    </span>

                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium border font-mono ${
                      dep.is_event_compressed
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 font-semibold'
                        : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    }`}>
                      {dep.service_status || 'On Time'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ─── Full-Day Timetable Section ─── */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 md:p-6 shadow-sm space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <h3 className="text-base md:text-lg font-bold text-white flex items-center gap-2">
              <Calendar className="w-4 h-4 text-cyan-400" />
              Full-Day Timetable
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700 font-mono">
                {summary.day_type}
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Complete chronological departures from {summary.origin_name} to {summary.destination_name}.
            </p>
          </div>

          {/* Date Selector & Search Box */}
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="relative">
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-700 text-slate-200 text-xs font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter time (e.g. 08:30)..."
                className="pl-8 pr-3 py-1.5 rounded-xl bg-slate-950 border border-slate-700 text-slate-200 text-xs placeholder-slate-500 focus:outline-none focus:border-cyan-500 w-44"
              />
            </div>
          </div>
        </div>

        {/* Time Period Filter Pills */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-slate-400 flex items-center gap-1 mr-1">
            <Filter className="w-3.5 h-3.5" /> Time Window:
          </span>
          {PERIOD_FILTERS.map((p) => {
            const isActive = periodFilter === p.id;
            return (
              <button
                key={p.id}
                onClick={() => setPeriodFilter(p.id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium transition border flex items-center gap-1.5 ${
                  isActive
                    ? 'bg-slate-800 text-cyan-300 border-cyan-500/50 font-bold shadow-sm'
                    : 'bg-slate-950/50 text-slate-400 border-slate-800 hover:text-slate-200 hover:bg-slate-800/40'
                }`}
              >
                <span>{p.label}</span>
                <span className="text-[10px] text-slate-500 font-mono">({p.timeRange})</span>
              </button>
            );
          })}
        </div>

        {/* Departures Table */}
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/80 text-slate-400 uppercase font-mono text-[10px] border-b border-slate-800">
              <tr>
                <th className="px-4 py-3 font-semibold">#</th>
                <th className="px-4 py-3 font-semibold">Departure Time (12h)</th>
                <th className="px-4 py-3 font-semibold">Time (24h)</th>
                <th className="px-4 py-3 font-semibold">Destination Terminal</th>
                <th className="px-4 py-3 font-semibold">Platform</th>
                <th className="px-4 py-3 font-semibold">Headway Gap</th>
                <th className="px-4 py-3 font-semibold">Active / Stabled Fleet</th>
                <th className="px-4 py-3 font-semibold">Data Classification</th>
                <th className="px-4 py-3 font-semibold">Service Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {filteredAllDepartures.length === 0 ? (
                <tr>
                  <td colSpan="9" className="px-4 py-8 text-center text-slate-400">
                    No departures match the selected filters.
                  </td>
                </tr>
              ) : (
                filteredAllDepartures.map((dep, index) => {
                  const isUpcoming = dep.departure_seconds >= currentTimeSecs;
                  return (
                    <tr
                      key={dep.trip_id || dep.departure_time + index}
                      className={`hover:bg-slate-800/40 transition ${
                        isUpcoming ? 'text-slate-200' : 'text-slate-500 opacity-70'
                      }`}
                    >
                      <td className="px-4 py-2.5 text-slate-500">{index + 1}</td>
                      <td className="px-4 py-2.5 font-bold text-white flex items-center gap-1.5">
                        <Clock className="w-3 h-3 text-cyan-400" />
                        {dep.departure_time_12h}
                        {isUpcoming && index === 0 && (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 font-sans font-bold">
                            Next
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400">{dep.departure_time}</td>
                      <td className="px-4 py-2.5 font-sans font-medium text-slate-200">
                        {dep.destination_name}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 font-sans">{dep.platform}</td>
                      <td className="px-4 py-2.5">
                        {dep.headway_min ? (
                          <div className="flex flex-col gap-0.5">
                            <span className={`px-2 py-0.5 rounded text-[11px] font-bold font-mono inline-block w-fit ${
                              dep.headway_min <= 3.5
                                ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                                : dep.headway_min <= 6.0
                                ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30'
                                : dep.headway_min <= 9.0
                                ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                                : 'bg-slate-800 text-slate-400 border border-slate-700'
                            }`}>
                              +{dep.headway_min}m
                            </span>
                            {dep.is_event_compressed && dep.headway_compression_min > 0 && (
                              <span className="text-[9px] text-emerald-400 font-bold font-mono flex items-center gap-0.5" title={`Compressed from ${dep.base_headway_min}m base`}>
                                <Zap className="w-2.5 h-2.5" />
                                -{dep.headway_compression_min}m surge
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-slate-300 font-sans">
                        {dep.active_trains_corridor ? (
                          <div className="flex items-center gap-1.5 font-mono text-[11px]">
                            <span className="text-cyan-300 font-bold">
                              {dep.active_trains_corridor} Active
                            </span>
                            <span className="text-slate-600">•</span>
                            <span className="text-amber-400 font-medium">
                              {dep.stabled_at_depot !== undefined ? `${dep.stabled_at_depot} Stabled` : `${dep.stationed_trains_network} Net`}
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        {scheduleMode === 'official' ? (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 font-sans">
                            Official Scheduled
                          </span>
                        ) : (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 font-sans">
                            Estimated
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 font-sans">
                        {dep.is_event_compressed ? (
                          <span
                            className="text-emerald-400 font-medium flex items-center gap-1 text-[11px]"
                            title={dep.event_name ? `${dep.event_name} (${dep.event_phase || 'Crowd Surge'})` : 'Event Crowd Surge'}
                          >
                            <Zap className="w-3 h-3 text-emerald-400 animate-pulse flex-shrink-0" />
                            <span className="truncate max-w-[130px] font-mono">{dep.service_status || 'Event Surge'}</span>
                          </span>
                        ) : dep.service_status && dep.service_status !== 'Normal Service' && dep.service_status !== 'Optimal Cadence' ? (
                          <span className="text-cyan-300 flex items-center gap-1 text-[11px]">
                            <CheckCircle2 className="w-3 h-3 text-cyan-400 flex-shrink-0" />
                            <span className="font-mono">{dep.service_status}</span>
                          </span>
                        ) : (
                          <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                            <CheckCircle2 className="w-3 h-3 flex-shrink-0" />
                            Normal Service
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Mandatory Data Reliability & Source Attribution Footer ─── */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 text-xs text-slate-400 space-y-3">
        <div className="flex items-center gap-2 text-slate-200 font-semibold border-b border-slate-800/80 pb-2.5">
          <Info className="w-4 h-4 text-cyan-400" />
          <span>Official Data Verification & Operating Standards</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-[11px] leading-relaxed">
          <div>
            <div className="text-slate-300 font-bold mb-1 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
              1. Type 1: Official Scheduled
            </div>
            <p>
              Directly sourced from the official Hyderabad Metro Rail Limited (HMRL) GTFS specification published via Open Data Telangana. Verified for all 57 stations across Red, Blue, and Green corridors.
            </p>
            <div className="mt-1 text-slate-500 font-mono">
              Last Verified: {classification.last_verified || 'October 2026'}
            </div>
          </div>

          <div>
            <div className="text-slate-300 font-bold mb-1 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              2. Type 2: Estimated Frequency Model
            </div>
            <p>
              Calculated dynamically via demand-capacity equations factoring real-time weather, city events, and strict 57-train global fleet ceiling with depot stabling at Miyapur, Uppal, and MGBS sidings when crowd levels decrease.
            </p>
            <div className="mt-1 text-slate-500 font-mono">
              Source: HMRL Dynamic Optimization Engine
            </div>
          </div>

          <div>
            <div className="text-slate-300 font-bold mb-1 flex items-center gap-1">
              <Radio className="w-3.5 h-3.5 text-rose-400" />
              3. Type 3: Live Telemetry Status
            </div>
            <p>
              HMRL operates on internal CBTC / SCADA signaling. A public GTFS-RT feed is restricted; countdowns reflect verified timetable timing rather than external telemetry.
            </p>
            <div className="mt-1 text-slate-500 font-mono">
              Provider: {liveStatus.provider}
            </div>
          </div>
        </div>

        <div className="pt-2 border-t border-slate-800 flex flex-wrap items-center justify-between text-[11px] text-slate-500">
          <span>
            Official Publisher: <span className="text-slate-300 font-medium">L&T Metro Rail (Hyderabad) Limited & HMRL</span>
          </span>
          <a
            href="https://www.ltmetro.com/"
            target="_blank"
            rel="noreferrer"
            className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition font-medium"
          >
            Visit Official L&T Metro Website <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>
    </div>
  );
}
