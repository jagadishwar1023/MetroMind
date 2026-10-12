import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 15000,
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

export default api;
