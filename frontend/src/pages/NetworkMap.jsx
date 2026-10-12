import React, { useEffect, useState, useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { getStations, autoOptimize } from '../api/client';
import DemandChart from '../components/DemandChart';
import LoadingSpinner from '../components/LoadingSpinner';
import { getDateOffset, shiftDate, formatDate } from '../utils/dateUtils';
import { Calendar, ChevronLeft, ChevronRight, Zap, ExternalLink, MapPin, Clock, Users, Train, Sparkles, Layers } from 'lucide-react';

// Fix leaflet default icon issue if markers are used later
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const CORRIDOR_COLORS = {
  RED: '#E31E24',
  BLUE: '#007ABB',
  GREEN: '#009846',
  MULTIPLE: '#800080' // Purple for interchanges
};

// Zero-API-Key Map Tile Providers (100% free, no token needed)
const MAP_THEMES = {
  'esri-dark': {
    id: 'esri-dark',
    name: 'Dark Canvas (Esri)',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
  },
  'osm-dark': {
    id: 'osm-dark',
    name: 'Dark OSM',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
  'osm-standard': {
    id: 'osm-standard',
    name: 'Standard OSM',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
};

export default function NetworkMap() {
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  const [selectedStation, setSelectedStation] = useState('HTC');
  const [selectedDate, setSelectedDate] = useState(getDateOffset(0));
  const [selectedHour, setSelectedHour] = useState(18);
  const [optimizationData, setOptimizationData] = useState(null);
  const [dataLoading, setDataLoading] = useState(false);
  const [mapTheme, setMapTheme] = useState('esri-dark');

  // Quick date presets
  const dateButtons = [
    { label: 'Today', offset: 0 },
    { label: 'Tomorrow', offset: 1 },
    { label: '+2 Days', offset: 2 },
    { label: '+3 Days', offset: 3 },
    { label: '+5 Days', offset: 5 },
  ];

  // 1. Fetch initial station directory
  useEffect(() => {
    fetchStations();
  }, []);

  const fetchStations = async () => {
    try {
      const data = await getStations();
      setStations(data);
      if (data.length > 0 && !selectedStation) {
        setSelectedStation(data[0].stop_id);
      }
      setLoading(false);
    } catch (err) {
      setError('Failed to load stations.');
      setLoading(false);
    }
  };

  // 2. Fetch full event-augmented network forecast for selectedDate
  useEffect(() => {
    fetchNetworkDemand(selectedDate);
  }, [selectedDate]);

  const fetchNetworkDemand = async (dateStr) => {
    setDataLoading(true);
    try {
      const res = await autoOptimize({ date: dateStr });
      setOptimizationData(res);
      
      // If currently selected station has no events, but another station does, default to event station if newly chosen
      const events = res?.events_used || [];
      if (events.length > 0 && (!selectedStation || selectedStation === 'AME')) {
        const evStation = events[0].nearest_station?.stop_id;
        if (evStation) setSelectedStation(evStation);
      }
    } catch (err) {
      console.error('Failed to load network demand data:', err);
    } finally {
      setDataLoading(false);
    }
  };

  const handleShiftDate = (days) => {
    setSelectedDate(shiftDate(selectedDate, days));
  };

  // Set of station IDs that have active events on selectedDate
  const eventStationMap = useMemo(() => {
    const map = new Map();
    if (!optimizationData?.events_used) return map;
    for (const ev of optimizationData.events_used) {
      const sid = ev.nearest_station?.stop_id;
      if (sid) {
        if (!map.has(sid)) map.set(sid, []);
        map.get(sid).push(ev);
      }
    }
    return map;
  }, [optimizationData]);

  // Events affecting the currently selected station
  const activeEventsForStation = useMemo(() => {
    return eventStationMap.get(selectedStation) || [];
  }, [eventStationMap, selectedStation]);

  // Demand profile for the currently selected station across all hours
  const stationDemandProfile = optimizationData?.station_demands?.[selectedStation];

  // Specific forecast for selected hour
  const currentHourBase = stationDemandProfile?.baseline?.[selectedHour] || 0;
  const currentHourSurge = stationDemandProfile?.event_surge?.[selectedHour] || 0;
  const currentHourTotal = stationDemandProfile?.predicted?.[selectedHour] || (currentHourBase + currentHourSurge);

  // Determine current recommended headway & trains per hour
  const selectedStationObj = stations.find(s => s.stop_id === selectedStation);
  const primaryCorridor = selectedStationObj?.corridors?.[0] || 'BLUE';
  
  const corridorHeadways = optimizationData?.directional_headways?.[primaryCorridor] || [];
  const hourHeadwayInfo = corridorHeadways.find(h => h.hour === selectedHour);
  const recommendedHeadway = hourHeadwayInfo?.inbound_headway || hourHeadwayInfo?.baseline_headway || 5.0;
  const trainsPerHour = Math.round((60 / recommendedHeadway) * 10) / 10;

  // 24-hour profile chart data with baseline and event surge breakdown
  const chartData = useMemo(() => {
    if (!stationDemandProfile) return [];
    const points = [];
    for (let h = 5; h <= 23; h++) {
      const base = stationDemandProfile.baseline?.[h] || 0;
      const surge = stationDemandProfile.event_surge?.[h] || 0;
      const total = stationDemandProfile.predicted?.[h] || (base + surge);
      points.push({
        hour: h,
        baseline: base,
        event_surge: surge,
        passengers: total,
      });
    }
    return points;
  }, [stationDemandProfile]);

  const getStationColor = (station) => {
    if (eventStationMap.has(station.stop_id)) return '#f97316'; // Highlight event stations in bright amber
    if (station.corridors.length > 1) return CORRIDOR_COLORS.MULTIPLE;
    return CORRIDOR_COLORS[station.corridors[0]] || '#333';
  };

  const getStationRadius = (station) => {
    const isSelected = station.stop_id === selectedStation;
    const hasEvent = eventStationMap.has(station.stop_id);
    let r = Math.max(6, (station.base_daily_passengers / 4500));
    if (hasEvent) r += 5;
    if (isSelected) r += 3;
    return r;
  };

  if (loading) return <LoadingSpinner />;
  if (error) return <div className="text-red-500 p-6">{error}</div>;

  return (
    <div className="flex flex-col lg:flex-row gap-6 h-full text-slate-100">
      {/* ─── LEFT: Network Map View ─── */}
      <div className="flex-1 bg-slate-900 rounded-xl border border-slate-800 shadow-xl overflow-hidden relative" style={{ minHeight: '620px' }}>
        
        {/* Floating Map Legend & Summary Pill */}
        <div className="absolute top-4 left-4 z-[400] bg-slate-900/90 backdrop-blur border border-slate-700/80 px-3.5 py-2.5 rounded-xl text-xs space-y-1.5 shadow-2xl">
          <div className="font-bold text-white flex items-center gap-1.5">
            <Train className="w-3.5 h-3.5 text-cyan-400" />
            <span>Hyderabad Metro Rail Network</span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-slate-300">
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-[#E31E24]" /> Red
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-[#007ABB]" /> Blue
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-full bg-[#009846]" /> Green
            </span>
            <span className="flex items-center gap-1 text-orange-400 font-semibold">
              <span className="w-2.5 h-2.5 rounded-full bg-orange-500 animate-pulse" /> ⚡ Event Surge
            </span>
          </div>
        </div>

        {/* Floating Map Theme Selector */}
        <div className="absolute top-4 right-4 z-[400] bg-slate-900/90 backdrop-blur border border-slate-700/80 p-1 rounded-xl text-xs flex items-center gap-1 shadow-2xl">
          <span className="text-[10px] text-slate-400 font-semibold px-1.5 flex items-center gap-1">
            <Layers className="w-3 h-3 text-cyan-400" />
            <span>Map:</span>
          </span>
          <button
            type="button"
            onClick={() => setMapTheme('esri-dark')}
            className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold transition ${
              mapTheme === 'esri-dark'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            Dark Canvas
          </button>
          <button
            type="button"
            onClick={() => setMapTheme('osm-dark')}
            className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold transition ${
              mapTheme === 'osm-dark'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            Dark OSM
          </button>
          <button
            type="button"
            onClick={() => setMapTheme('osm-standard')}
            className={`px-2 py-0.5 rounded-lg text-[11px] font-semibold transition ${
              mapTheme === 'osm-standard'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            Standard OSM
          </button>
        </div>

        <style>
          {`
            .osm-dark-tiles .leaflet-tile-pane {
              filter: brightness(0.65) invert(1) contrast(2.5) hue-rotate(200deg) saturate(0.3) brightness(0.7);
            }
          `}
        </style>

        <MapContainer
          center={[17.4100, 78.4500]}
          zoom={12}
          className={mapTheme === 'osm-dark' ? 'osm-dark-tiles w-full h-full' : 'w-full h-full'}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            key={mapTheme}
            attribution={MAP_THEMES[mapTheme].attribution}
            url={MAP_THEMES[mapTheme].url}
          />
          {stations.map(station => {
            const hasEvent = eventStationMap.has(station.stop_id);
            const isSelected = station.stop_id === selectedStation;
            const stationEvents = eventStationMap.get(station.stop_id) || [];

            return (
              <CircleMarker
                key={station.stop_id}
                center={[station.stop_lat, station.stop_lon]}
                pathOptions={{ 
                  fillColor: getStationColor(station),
                  color: hasEvent ? '#fed7aa' : (isSelected ? '#38bdf8' : 'white'),
                  weight: hasEvent ? 3 : (isSelected ? 3 : 1.5),
                  fillOpacity: hasEvent ? 0.95 : 0.85
                }}
                radius={getStationRadius(station)}
                eventHandlers={{
                  click: () => {
                    setSelectedStation(station.stop_id);
                  },
                }}
              >
                <Popup>
                  <div className="text-slate-900 min-w-[200px]">
                    <div className="font-bold text-sm text-slate-900">{station.stop_name}</div>
                    <div className="text-xs text-slate-600 font-medium">{station.corridors.join(', ')} Line</div>
                    <div className="text-xs text-slate-500 mt-1">Base Daily Commuters: {station.base_daily_passengers?.toLocaleString()}</div>
                    
                    {hasEvent && (
                      <div className="mt-2.5 pt-2 border-t border-slate-200">
                        <div className="text-xs font-bold text-orange-600 flex items-center gap-1">
                          ⚡ Event Surge Active on {formatDate(selectedDate)}
                        </div>
                        {stationEvents.map((ev, i) => (
                          <div key={i} className="text-[11px] text-slate-800 mt-1 bg-orange-50 p-1.5 rounded border border-orange-200">
                            <strong>{ev.name}</strong>
                            <div className="text-[10px] text-slate-600">Venue: {ev.venue_name}</div>
                            <div className="text-[10px] text-orange-700 font-semibold mt-0.5">
                              Metro Riders: +{ev.metro_riders?.toLocaleString()} pax
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <button
                      onClick={() => setSelectedStation(station.stop_id)}
                      className="mt-2 w-full text-center text-[11px] bg-slate-900 text-white py-1 rounded hover:bg-slate-800 transition"
                    >
                      View Hourly Demand Forecast
                    </button>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>
      
      {/* ─── RIGHT: Demand Forecast Side Panel ─── */}
      <div className="w-full lg:w-[420px] bg-slate-900/90 backdrop-blur-md rounded-2xl border border-slate-800 shadow-2xl p-5 overflow-y-auto flex flex-col max-h-[820px]">
        
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Users className="w-5 h-5 text-cyan-400" />
              Demand Forecast
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Live event-augmented passenger load models
            </p>
          </div>
          <span className="text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/25 px-2 py-0.5 rounded-full font-bold font-mono">
            ML POWERED
          </span>
        </div>

        {/* ── Date Navigation ── */}
        <div className="pt-4 pb-3 border-b border-slate-800/80">
          <div className="flex items-center gap-2 mb-2.5">
            <div className="inline-flex rounded-xl bg-slate-950/80 border border-slate-800 p-0.5">
              <button 
                onClick={() => handleShiftDate(-1)} 
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
                title="Previous Day"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <div className="flex items-center gap-1.5 px-2 py-0.5 text-xs font-semibold text-slate-200">
                <Calendar className="w-3.5 h-3.5 text-cyan-400" />
                <span>{formatDate(selectedDate)}</span>
              </div>
              <button 
                onClick={() => handleShiftDate(1)} 
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
                title="Next Day"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
            <input 
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-slate-950/80 border border-slate-800 text-slate-300 px-2 py-1 rounded-xl text-xs font-mono font-medium focus:ring-1 focus:ring-cyan-500 focus:outline-none ml-auto"
            />
          </div>

          {/* Quick Date Presets */}
          <div className="flex gap-1.5 flex-wrap">
            {dateButtons.map(db => {
              const dateVal = getDateOffset(db.offset);
              const isSelected = selectedDate === dateVal;
              return (
                <button
                  key={db.offset}
                  onClick={() => setSelectedDate(dateVal)}
                  className={`px-2.5 py-1 rounded-xl text-[11px] font-medium transition-all ${
                    isSelected
                      ? 'bg-cyan-600 text-white border border-cyan-500 shadow-md shadow-cyan-600/25 font-semibold'
                      : 'bg-slate-950/60 text-slate-400 hover:bg-slate-800/80 border border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {db.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Station Selector ── */}
        <div className="pt-3 pb-3">
          <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center justify-between">
            <span>Selected Station:</span>
            {activeEventsForStation.length > 0 && (
              <span className="text-[10px] bg-orange-500/15 text-orange-400 border border-orange-500/30 px-2 py-0.5 rounded-full font-bold">
                ⚡ Active Event Surge
              </span>
            )}
          </label>
          <select 
            className="w-full bg-slate-950/80 border border-slate-800 text-slate-200 rounded-xl p-2.5 text-xs focus:ring-1 focus:ring-cyan-500 focus:outline-none font-medium"
            value={selectedStation}
            onChange={(e) => setSelectedStation(e.target.value)}
          >
            {stations.map(s => {
              const hasEv = eventStationMap.has(s.stop_id);
              return (
                <option key={s.stop_id} value={s.stop_id}>
                  {hasEv ? '⚡ ' : ''}{s.stop_name} ({s.stop_id}) — {s.corridors.join('/')}
                </option>
              );
            })}
          </select>
        </div>

        {/* ── Hour Slider ── */}
        <div className="pb-4 border-b border-slate-800/80">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-300 mb-1">
            <span>Time of Day:</span>
            <span className="text-cyan-400 font-mono font-bold text-sm">{selectedHour}:00 hrs</span>
          </div>
          <input 
            type="range" 
            min="5" max="23" 
            className="w-full accent-cyan-500 cursor-pointer"
            value={selectedHour}
            onChange={(e) => setSelectedHour(parseInt(e.target.value))}
          />
          <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-0.5">
            <span>05:00 AM (First Train)</span>
            <span>23:00 PM (Last Train)</span>
          </div>
        </div>

        {/* ── Active Event Banner (If station has active event) ── */}
        {activeEventsForStation.length > 0 && (
          <div className="mt-4 p-3 bg-gradient-to-r from-orange-950/50 to-amber-950/40 rounded-xl border border-orange-500/40 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-orange-300 font-bold flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-orange-400" />
                Active Event Impacting Station
              </span>
              <span className="text-[10px] bg-orange-500/20 text-orange-300 border border-orange-500/30 px-1.5 py-0.2 rounded font-mono font-semibold">
                +{activeEventsForStation.reduce((acc, ev) => acc + (ev.metro_riders || 0), 0).toLocaleString()} Pax
              </span>
            </div>

            {activeEventsForStation.map((ev, i) => (
              <div key={i} className="bg-slate-900/80 p-2.5 rounded-lg border border-orange-500/20 text-[11px] space-y-1">
                <div className="font-semibold text-white flex items-center justify-between">
                  <span className="truncate pr-2">{ev.name}</span>
                  {ev.event_url && (
                    <a href={ev.event_url} target="_blank" rel="noreferrer" className="text-cyan-400 hover:text-cyan-300 shrink-0">
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>
                <div className="text-[10px] text-slate-400 flex items-center gap-1">
                  <MapPin className="w-3 h-3 text-slate-500" />
                  <span className="truncate">{ev.venue_name}</span>
                </div>
                <div className="text-[10px] text-slate-400 flex items-center gap-1">
                  <Clock className="w-3 h-3 text-slate-500" />
                  <span>Start: {ev.start_time?.substring(11, 16) || '19:00'} • End: {ev.end_time?.substring(11, 16) || '22:00'}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Forecast Metric Cards ── */}
        <div className="mt-4 space-y-3">
          <div className="bg-slate-800/60 p-4 rounded-xl border border-slate-700/60">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs text-slate-400 font-medium">Expected Passengers at {selectedHour}:00</span>
              {currentHourSurge > 0 && (
                <span className="text-[10px] bg-orange-500/20 text-orange-300 border border-orange-500/30 px-2 py-0.5 rounded font-bold font-mono">
                  ⚡ +{currentHourSurge.toLocaleString()} Event Surge
                </span>
              )}
            </div>
            
            <div className="text-3xl font-extrabold text-white font-mono">
              {currentHourTotal.toLocaleString()}
            </div>

            <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-700/40 text-[11px]">
              <span className="text-cyan-400">
                Base Commute: <strong>{currentHourBase.toLocaleString()}</strong>
              </span>
              {currentHourSurge > 0 ? (
                <span className="text-orange-400 font-semibold">
                  • Event Addition: <strong>+{currentHourSurge.toLocaleString()}</strong> ({Math.round((currentHourSurge / currentHourBase) * 100)}%)
                </span>
              ) : (
                <span className="text-slate-500">
                  • Regular commuter traffic
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-800/40 p-3 rounded-xl border border-slate-700/50">
              <div className="text-[10px] text-slate-400 font-semibold">Recommended Headway</div>
              <div className="text-xl font-bold text-cyan-400 mt-0.5 font-mono">
                {recommendedHeadway} min
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">{primaryCorridor} Corridor</div>
            </div>

            <div className="bg-slate-800/40 p-3 rounded-xl border border-slate-700/50">
              <div className="text-[10px] text-slate-400 font-semibold">Trains Per Hour</div>
              <div className="text-xl font-bold text-white mt-0.5 font-mono">
                {trainsPerHour} tph
              </div>
              <div className="text-[10px] text-slate-500 mt-0.5">Frequency Capacity</div>
            </div>
          </div>
        </div>

        {/* ── 24-Hour Profile Chart ── */}
        <div className="mt-5 pt-4 border-t border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wide">
              24-Hour Passenger Demand Profile
            </h3>
            {currentHourSurge > 0 && (
              <span className="text-[10px] text-orange-400 font-semibold flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-orange-500 inline-block" /> Event Surge Active
              </span>
            )}
          </div>

          {dataLoading ? (
            <div className="py-12"><LoadingSpinner /></div>
          ) : chartData.length > 0 ? (
            <div className="bg-slate-950/40 p-2.5 rounded-xl border border-slate-800/80">
              <DemandChart data={chartData} height={190} color="#06b6d4" />
              <div className="flex items-center justify-center gap-4 text-[10px] text-slate-400 mt-2">
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1.5 bg-cyan-400 rounded-sm inline-block" /> Base Commute
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1.5 bg-orange-500 rounded-sm inline-block" /> ⚡ Event Surge
                </span>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-xs text-slate-500">No profile data available</div>
          )}
        </div>

      </div>
    </div>
  );
}
