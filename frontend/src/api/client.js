import axios from 'axios';

export const getApiBaseUrl = () => {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem('METROMIND_API_URL');
    if (saved && saved.trim()) return saved.trim().replace(/\/+$/, '');
  }
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl && envUrl.trim()) return envUrl.trim().replace(/\/+$/, '');
  return 'http://localhost:8000';
};

export const setApiBaseUrl = (url) => {
  if (typeof window !== 'undefined') {
    if (!url || !url.trim()) {
      localStorage.removeItem('METROMIND_API_URL');
    } else {
      localStorage.setItem('METROMIND_API_URL', url.trim().replace(/\/+$/, ''));
    }
  }
};

const api = axios.create({
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000, // 60s accommodates cloud free-tier cold start wake-up
});

api.interceptors.request.use((config) => {
  config.baseURL = getApiBaseUrl();
  return config;
});

// ── Existing endpoints ──────────────────────────────────────
export const getStations       = () => api.get('/stations').then(r => r.data);
export const getCorridors      = () => api.get('/corridors').then(r => r.data);
export const getCurrentSchedule= (corridor, service) => api.get(`/schedule/current?corridor=${corridor}&service=${service}`).then(r => r.data);
export const predictDemand     = (payload) => api.post('/predict/demand', payload).then(r => r.data);
export const predictEvent      = (payload) => api.post('/predict/event', payload).then(r => r.data);
export const optimize          = (payload) => api.post('/optimize', payload).then(r => r.data);
export const getVenues         = () => api.get('/venues').then(r => r.data);

// ── Phase 2/3 new endpoints ─────────────────────────────────
export const getHealth         = () => api.get('/health').then(r => r.data);
export const getLiveWeather    = () => api.get('/weather/live').then(r => r.data);
export const getLiveEvents     = (withinHours = 48) => api.get(`/events/live?within_hours=${withinHours}`).then(r => r.data);
export const getActiveEvents   = () => api.get('/events/active').then(r => r.data);
export const getActiveAnomalies= () => api.get('/anomalies/active').then(r => r.data);
export const predictDirectional= (payload) => api.post('/predict/directional', payload).then(r => r.data);
export const predictDemandLive = (payload) => api.post('/predict/demand-with-live-data', payload).then(r => r.data);
export const detectAnomaly     = (payload) => api.post('/anomalies/detect', payload).then(r => r.data);
export const getSchedulerStatus= () => api.get('/scheduler/status').then(r => r.data);

export const autoOptimize    = (payload = {}) => api.post('/auto-optimize', payload).then(r => r.data);
export const createManualEvent= (payload) => api.post('/manual-events', payload).then(r => r.data);
export const deleteManualEvent= (id) => api.delete(`/manual-events/${id}`).then(r => r.data);
export const getManualEvents  = (date) => api.get(`/manual-events${date ? `?date=${date}` : ''}`).then(r => r.data);

// ── Unified Disruption & Live Traffic Feed ───────────────────
export const getLiveDisruptions = (params = {}) => api.get('/disruptions/live', { params }).then(r => r.data);
export const refreshDisruptions = () => api.post('/disruptions/refresh').then(r => r.data);

// ── Metro Train Schedule & Terminal Departures ───────────────
export const getMetroScheduleLines = () => api.get('/metro-schedule/lines').then(r => r.data);
export const getMetroDepartures = (params = {}) => api.get('/metro-schedule/departures', { params }).then(r => r.data);
export const getMetroStationSequence = (line, directionId = 0) => api.get(`/metro-schedule/station-sequence?line=${line}&direction_id=${directionId}`).then(r => r.data);
export const getMetroScheduleEvents = (date) => api.get(`/metro-schedule/events${date ? `?target_date=${date}` : ''}`).then(r => r.data);
export const createMetroScheduleEvent = (payload) => api.post('/metro-schedule/events', payload).then(r => r.data);
export const deleteMetroScheduleEvent = (id) => api.delete(`/metro-schedule/events/${id}`).then(r => r.data);
export const resetMetroScheduleEvents = () => api.post('/metro-schedule/events/reset').then(r => r.data);

export default api;
