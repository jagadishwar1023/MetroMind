import React, { useState, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, Tooltip, Marker, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { RED_LINE_COORDS, BLUE_LINE_COORDS, GREEN_LINE_COORDS } from '../data/corridorCoordinates';
import { autoOptimize, getStations } from '../api/client';
import { getDateOffset, shiftDate, formatDate } from '../utils/dateUtils';
import LoadingSpinner from './LoadingSpinner';
import { Calendar, ChevronLeft, ChevronRight, X, ExternalLink, MapPin, Footprints, Clock, Users, Train, Sparkles, Navigation, Layers } from 'lucide-react';

const HYDERABAD_CENTER = [17.4200, 78.4500];

// Zero-API-Key Map Tile Providers (100% free, no registration or token needed)
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

// Custom Event Pin Icon for Leaflet
const createEventIcon = (eventType = 'other') => {
  return L.divIcon({
    className: 'custom-event-pin',
    html: `
      <div style="
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 38px;
        height: 38px;
        background: linear-gradient(135deg, #f97316 0%, #ea580c 100%);
        border: 2.5px solid #ffffff;
        border-radius: 50%;
        box-shadow: 0 4px 14px rgba(249, 115, 22, 0.6);
        cursor: pointer;
      ">
        <span style="font-size: 18px; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.4));">⚡</span>
        <div style="
          position: absolute;
          inset: -6px;
          border-radius: 50%;
          border: 2px dashed #f97316;
          animation: spin 6s linear infinite;
          opacity: 0.8;
        "></div>
      </div>
    `,
    iconSize: [38, 38],
    iconAnchor: [19, 19],
    popupAnchor: [0, -22],
  });
};

// Map Recenter / Pan Helper Component
function MapController({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.flyTo(center, zoom || 13, { duration: 1.2 });
    }
  }, [center, zoom, map]);
  return null;
}

export default function EventProximityMap({ onClose, initialDate }) {
  const [selectedDate, setSelectedDate] = useState(initialDate || getDateOffset(0));
  const [stations, setStations] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeEventIndex, setActiveEventIndex] = useState(0);
  const [mapFocus, setMapFocus] = useState(null);
  const [mapTheme, setMapTheme] = useState('esri-dark');

  // Quick date presets
  const dateButtons = [
    { label: 'Today', offset: 0 },
    { label: 'Tomorrow', offset: 1 },
    { label: '+2 Days', offset: 2 },
    { label: '+3 Days', offset: 3 },
    { label: '+5 Days', offset: 5 },
  ];

  // 1. Load stations
  useEffect(() => {
    getStations().then(res => {
      if (Array.isArray(res)) setStations(res);
    }).catch(console.error);
  }, []);

  // 2. Fetch events and optimization data for selectedDate
  useEffect(() => {
    fetchDateEvents(selectedDate);
  }, [selectedDate]);

  const fetchDateEvents = async (dateStr) => {
    setLoading(true);
    try {
      const res = await autoOptimize({ date: dateStr });
      setData(res);
      const events = res.events_used || [];
      if (events.length > 0) {
        setActiveEventIndex(0);
        const firstEv = events[0];
        const vLat = parseFloat(firstEv.venue_lat || 17.4063);
        const vLon = parseFloat(firstEv.venue_lon || 78.5480);
        setMapFocus({ center: [vLat, vLon], zoom: 13 });
      }
    } catch (err) {
      console.error('Failed to load events for date:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleShiftDate = (days) => {
    setSelectedDate(shiftDate(selectedDate, days));
  };

  const events = data?.events_used || [];

  // Map station dictionary for instant lookup
  const stationDict = useMemo(() => {
    const map = {};
    for (const s of stations) {
      map[s.stop_id] = s;
    }
    return map;
  }, [stations]);

  // Focus on a specific event
  const focusEvent = (ev, idx) => {
    setActiveEventIndex(idx);
    const vLat = parseFloat(ev.venue_lat || 17.4063);
    const vLon = parseFloat(ev.venue_lon || 78.5480);
    setMapFocus({ center: [vLat, vLon], zoom: 14 });
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden text-slate-100">
        
        {/* ── Top Modal Header ── */}
        <div className="px-5 py-4 border-b border-slate-800 bg-slate-950/80 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-orange-500/10 rounded-xl border border-orange-500/20 text-orange-400">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                Event & Metro Proximity Map
                <span className="text-xs bg-orange-500/20 text-orange-300 border border-orange-500/30 px-2 py-0.5 rounded-full font-mono">
                  {events.length} {events.length === 1 ? 'Event' : 'Events'} Active
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Visualizing city event venues, nearest metro station connections, and walking distances
              </p>
            </div>
          </div>

          {/* Date Selector Row */}
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 bg-slate-800/80 p-1 rounded-xl border border-slate-700">
              <button 
                onClick={() => handleShiftDate(-1)} 
                className="p-1 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition"
                title="Previous Day"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <input 
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-white px-2 py-1 rounded-lg text-xs font-mono font-medium focus:ring-1 focus:ring-cyan-500 focus:outline-none"
              />
              <button 
                onClick={() => handleShiftDate(1)} 
                className="p-1 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition"
                title="Next Day"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            <div className="hidden md:flex gap-1">
              {dateButtons.map(db => {
                const dateVal = getDateOffset(db.offset);
                const isSelected = selectedDate === dateVal;
                return (
                  <button
                    key={db.offset}
                    onClick={() => setSelectedDate(dateVal)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                      isSelected
                        ? 'bg-orange-500/20 text-orange-300 border border-orange-500/40'
                        : 'bg-slate-800/60 text-slate-400 hover:bg-slate-800 border border-slate-700/60'
                    }`}
                  >
                    {db.label}
                  </button>
                );
              })}
            </div>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="p-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition ml-2 border border-slate-700"
              title="Close Map"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* ── Main Body: Map (Left/Center) + Events Sidebar (Right) ── */}
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden relative">
          
          {/* Map Area */}
          <div className="flex-1 relative bg-slate-950">
            {loading && (
              <div className="absolute inset-0 z-[1000] bg-slate-950/70 backdrop-blur-sm flex items-center justify-center">
                <LoadingSpinner />
              </div>
            )}

            {/* Floating Map Legend */}
            <div className="absolute top-4 left-4 z-[400] bg-slate-900/90 backdrop-blur-md border border-slate-700/80 px-3.5 py-2.5 rounded-xl text-xs space-y-1.5 shadow-2xl">
              <div className="font-bold text-white flex items-center gap-1.5">
                <Train className="w-3.5 h-3.5 text-cyan-400" />
                <span>Hyderabad Metro Corridors</span>
              </div>
              <div className="flex items-center gap-3 text-[11px] text-slate-300">
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#ef4444]" /> Red Line
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#3b82f6]" /> Blue Line
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#22c55e]" /> Green Line
                </span>
              </div>
              <div className="pt-1 border-t border-slate-800 flex items-center gap-2 text-[10px] text-slate-400">
                <span className="flex items-center gap-1 text-orange-400 font-semibold">
                  <span className="w-2 h-2 rounded-full bg-orange-500 animate-ping inline-block" /> ⚡ Event Venue
                </span>
                <span>•</span>
                <span className="text-amber-300 font-mono">
                  - - - Nearest Metro Walk Distance
                </span>
              </div>
            </div>

            {/* Floating Map Theme Selector */}
            <div className="absolute top-4 right-4 z-[400] bg-slate-900/90 backdrop-blur-md border border-slate-700/80 p-1 rounded-xl text-xs flex items-center gap-1 shadow-2xl">
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
              center={HYDERABAD_CENTER}
              zoom={12}
              className={mapTheme === 'osm-dark' ? 'osm-dark-tiles w-full h-full' : 'w-full h-full'}
              style={{ height: '100%', width: '100%' }}
              zoomControl={true}
            >
              {mapFocus && <MapController center={mapFocus.center} zoom={mapFocus.zoom} />}

              <TileLayer
                key={mapTheme}
                url={MAP_THEMES[mapTheme].url}
                attribution={MAP_THEMES[mapTheme].attribution}
              />

              {/* 1. Metro Corridor Polylines */}
              <Polyline 
                positions={RED_LINE_COORDS || []} 
                pathOptions={{ color: '#ef4444', weight: 4.5, opacity: 0.85 }} 
              />
              <Polyline 
                positions={BLUE_LINE_COORDS || []} 
                pathOptions={{ color: '#3b82f6', weight: 4.5, opacity: 0.85 }} 
              />
              <Polyline 
                positions={GREEN_LINE_COORDS || []} 
                pathOptions={{ color: '#22c55e', weight: 4.5, opacity: 0.85 }} 
              />

              {/* 2. All 57 Metro Stations */}
              {stations.map(station => {
                const isNearestToAnyEvent = events.some(e => e.nearest_station?.stop_id === station.stop_id);
                const primaryCorridor = station.corridors?.[0] || 'RED';
                const corridorColor = primaryCorridor === 'BLUE' ? '#38bdf8' : (primaryCorridor === 'GREEN' ? '#4ade80' : '#f87171');

                return (
                  <CircleMarker
                    key={station.stop_id}
                    center={[station.stop_lat, station.stop_lon]}
                    radius={isNearestToAnyEvent ? 8 : 4.5}
                    pathOptions={{
                      fillColor: isNearestToAnyEvent ? '#f97316' : corridorColor,
                      color: isNearestToAnyEvent ? '#ffffff' : '#0f172a',
                      weight: isNearestToAnyEvent ? 2.5 : 1.5,
                      fillOpacity: 0.9,
                    }}
                  >
                    <Popup className="bg-slate-900 text-white">
                      <div className="p-1 text-slate-900">
                        <strong className="text-sm font-bold block">{station.stop_name}</strong>
                        <div className="text-xs text-slate-600 font-medium">{station.corridors?.join(', ')} Line</div>
                        <div className="text-[11px] text-slate-500 mt-1">
                          Base Daily Passengers: {station.base_daily_passengers?.toLocaleString()}
                        </div>
                        {isNearestToAnyEvent && (
                          <div className="mt-2 pt-1 border-t border-slate-200 text-xs font-bold text-orange-600">
                            ⚡ Connected Event Feeder Station
                          </div>
                        )}
                      </div>
                    </Popup>
                  </CircleMarker>
                );
              })}

              {/* 3. Event Markers & Proximity Connector Lines */}
              {events.map((ev, idx) => {
                const vLat = parseFloat(ev.venue_lat || 17.4063);
                const vLon = parseFloat(ev.venue_lon || 78.5480);
                const nearestSid = ev.nearest_station?.stop_id;
                const nearestStn = stationDict[nearestSid] || ev.nearest_station;
                const stnLat = nearestStn?.stop_lat || nearestStn?.lat;
                const stnLon = nearestStn?.stop_lon || nearestStn?.lon;
                
                const distKm = ev.distance_to_nearest_metro_km || ev.nearest_station?.distance_km || 1.0;
                const walkMin = Math.round(distKm * 12);
                const isSelected = activeEventIndex === idx;

                const connectorPositions = (stnLat && stnLon) ? [
                  [vLat, vLon],
                  [stnLat, stnLon],
                ] : null;

                const midLat = connectorPositions ? (vLat + stnLat) / 2 : vLat;
                const midLon = connectorPositions ? (vLon + stnLon) / 2 : vLon;

                return (
                  <React.Fragment key={`event-prox-${ev.id || idx}`}>
                    {/* Dashed Proximity Line to Nearest Metro */}
                    {connectorPositions && (
                      <Polyline
                        positions={connectorPositions}
                        pathOptions={{
                          color: isSelected ? '#fbbf24' : '#f97316',
                          weight: isSelected ? 3.5 : 2.5,
                          dashArray: '6, 8',
                          opacity: 0.9,
                        }}
                      >
                        <Tooltip permanent direction="top" className="bg-slate-900 text-white border-0 shadow-lg text-[10px]">
                          <span>🚶 <strong>{distKm} km</strong> (~{walkMin}m walk)</span>
                        </Tooltip>
                      </Polyline>
                    )}

                    {/* Event Venue Marker Pin */}
                    <Marker
                      position={[vLat, vLon]}
                      icon={createEventIcon(ev.event_type)}
                      eventHandlers={{
                        click: () => setActiveEventIndex(idx),
                      }}
                    >
                      <Popup className="bg-slate-900 text-white">
                        <div className="p-1 text-slate-900 min-w-[220px]">
                          <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded bg-orange-100 text-orange-800">
                            {ev.event_type?.replace('_', ' ')}
                          </span>
                          <strong className="text-sm font-bold block text-slate-900 mt-1">{ev.name}</strong>
                          <div className="text-xs text-slate-600 mt-0.5">{ev.venue_name}</div>
                          
                          <div className="mt-2.5 pt-2 border-t border-slate-200 text-xs space-y-1">
                            <div className="flex justify-between text-slate-700">
                              <span>Nearest Metro:</span>
                              <strong className="text-cyan-700">{nearestStn?.stop_name || nearestSid}</strong>
                            </div>
                            <div className="flex justify-between text-slate-700">
                              <span>Proximity:</span>
                              <strong className="text-orange-700">{distKm} km ({walkMin} min walk)</strong>
                            </div>
                            <div className="flex justify-between text-slate-700">
                              <span>Metro Crowd Surge:</span>
                              <strong className="text-slate-900">+{ev.metro_riders?.toLocaleString()} pax</strong>
                            </div>
                          </div>

                          {ev.event_url && (
                            <a
                              href={ev.event_url}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-2.5 inline-flex items-center gap-1 text-[11px] text-cyan-600 hover:text-cyan-700 font-semibold"
                            >
                              <span>View Event Source / Tickets</span>
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                        </div>
                      </Popup>
                    </Marker>
                  </React.Fragment>
                );
              })}
            </MapContainer>
          </div>

          {/* ── Events List & Distance Sidebar (Right side, 340px) ── */}
          <div className="w-full lg:w-[360px] bg-slate-900 border-t lg:border-t-0 lg:border-l border-slate-800 p-4 overflow-y-auto flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wide">
                Active Events ({events.length})
              </span>
              <span className="text-[11px] text-slate-400">
                {formatDate(selectedDate)}
              </span>
            </div>

            {events.length === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400 space-y-2">
                <Calendar className="w-8 h-8 text-slate-600 mx-auto" />
                <p className="font-semibold text-slate-300">No Major Arena Events on this Date</p>
                <p className="text-[11px] text-slate-500">
                  Select another date above (e.g. Thu, Fri, or Saturday) to inspect event proximities.
                </p>
              </div>
            ) : (
              <div className="space-y-3 mt-3 flex-1 overflow-y-auto pr-1">
                {events.map((ev, i) => {
                  const isSelected = activeEventIndex === i;
                  const distKm = ev.distance_to_nearest_metro_km || ev.nearest_station?.distance_km || 1.0;
                  const walkMin = Math.round(distKm * 12);
                  const nearestStn = stationDict[ev.nearest_station?.stop_id] || ev.nearest_station;

                  return (
                    <div
                      key={ev.id || i}
                      onClick={() => focusEvent(ev, i)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-orange-950/40 border-orange-500/80 shadow-lg shadow-orange-950/30 ring-1 ring-orange-500/50'
                          : 'bg-slate-800/40 border-slate-700/60 hover:bg-slate-800 hover:border-slate-600'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="truncate flex-1">
                          <span className="text-[10px] font-bold uppercase tracking-wide px-1.5 py-0.2 rounded bg-orange-500/20 text-orange-300 border border-orange-500/30">
                            {ev.event_type?.replace('_', ' ')}
                          </span>
                          <h4 className="text-sm font-bold text-white mt-1 truncate">{ev.name}</h4>
                          <p className="text-[11px] text-slate-400 truncate mt-0.5">{ev.venue_name}</p>
                        </div>
                        {ev.event_url && (
                          <a
                            href={ev.event_url}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            className="p-1 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-700/60 transition"
                            title="Open ticket link"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>

                      {/* Nearest Metro Proximity Highlight */}
                      <div className="mt-2.5 pt-2 border-t border-slate-700/40 space-y-1.5 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] text-slate-400 flex items-center gap-1">
                            <Train className="w-3 h-3 text-cyan-400" /> Nearest Metro:
                          </span>
                          <strong className="text-cyan-300 font-semibold truncate max-w-[140px]">
                            {nearestStn?.stop_name || ev.nearest_station?.stop_id}
                          </strong>
                        </div>

                        <div className="flex items-center justify-between bg-slate-900/80 px-2 py-1.5 rounded-lg border border-slate-700/50">
                          <span className="text-[11px] text-amber-300 flex items-center gap-1 font-medium">
                            <Footprints className="w-3.5 h-3.5 text-amber-400" /> Walk Distance:
                          </span>
                          <strong className="text-orange-300 font-mono text-xs">
                            {distKm} km (~{walkMin}m walk)
                          </strong>
                        </div>

                        <div className="flex items-center justify-between text-[11px] text-slate-400">
                          <span className="flex items-center gap-1">
                            <Users className="w-3 h-3 text-slate-500" /> Expected Metro Surge:
                          </span>
                          <strong className="text-white font-mono">
                            +{ev.metro_riders?.toLocaleString()} pax
                          </strong>
                        </div>
                      </div>

                      <div className="mt-2 pt-1.5 flex items-center justify-between text-[10px] text-slate-500">
                        <span>Click card to center map</span>
                        <Navigation className="w-3 h-3 text-cyan-400" />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

        </div>

      </div>
    </div>
  );
}
