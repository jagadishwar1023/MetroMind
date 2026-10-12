from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Union, Dict, Any
import json
import urllib.parse
import pandas as pd
from datetime import datetime, date
import sys, os
from pathlib import Path
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
except Exception:
    pass

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

app = FastAPI(title='HMR Demand Optimization API', version='2.0.0')

app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

# ── Startup: load data ──────────────────────────────────────────────────────
from gtfs.loader import load_stops, get_station_route_map
from gtfs.headway import compute_headways, get_headway_dict
from models.event_impact import calculate_event_impact, rank_stations_by_impact, get_venues
from models.optimizer import optimize_schedule

STATION_META_PATH = Path(__file__).parent / 'data' / 'station_meta.json'
ACTIVE_ALERTS_PATH = Path(__file__).parent / 'data' / 'active_alerts.json'

_stops_df = None
_headways_wk = None
_headways_sa = None
_headways_su = None
_station_meta = None
_route_map = None
_demand_model = None
_directional_model = None
_anomaly_detector = None
_scheduler = None

@app.on_event('startup')
def startup():
    global _stops_df, _headways_wk, _headways_sa, _headways_su, _station_meta, _route_map, _demand_model, _directional_model, _anomaly_detector, _scheduler
    print('Loading GTFS data...')
    _stops_df = load_stops()
    _headways_wk = get_headway_dict('WK')
    _headways_sa = get_headway_dict('SA')
    _headways_su = get_headway_dict('SU')
    _route_map = get_station_route_map()
    if STATION_META_PATH.exists():
        with open(STATION_META_PATH) as f:
            _station_meta = json.load(f)
    try:
        from models.demand_model import get_model
        _demand_model = get_model()
        print('Demand model loaded.')
    except Exception as e:
        print(f'Demand model not loaded (run train_model.py first): {e}')
    try:
        from models.directional_model import DirectionalDemandModel
        _directional_model = DirectionalDemandModel()
        print('Directional model loaded.')
    except Exception as e:
        print(f'Directional model not loaded: {e}')
    try:
        from models.anomaly_detector import get_detector
        _anomaly_detector = get_detector()
        print('Anomaly detector loaded.')
    except Exception as e:
        print(f'Anomaly detector not loaded: {e}')
    # Initialize live weather from OpenWeatherMap
    try:
        from scrapers.weather_client import WeatherClient
        from scheduler.background_worker import WeatherCache
        _wc = WeatherClient()
        _curr = _wc.fetch_current()
        _fore = _wc.fetch_forecast(hours=24)
        WeatherCache.save(
            weather_code=_curr.get('weather_code', 0),
            temperature=_curr.get('temperature', 30.0),
            forecast_list=_fore
        )
        print(f"Live weather initialized: {_curr.get('temperature')}°C, {_curr.get('description')}")
    except Exception as _we:
        print(f"Weather initial sync: {_we}")
    # Start background scheduler
    try:
        from scheduler.background_worker import start_scheduler
        _scheduler = start_scheduler()
        print('Background scheduler started.')
    except Exception as e:
        print(f'Scheduler not started: {e}')
    print('Startup complete.')

@app.on_event('shutdown')
def shutdown():
    if _scheduler:
        from scheduler.background_worker import stop_scheduler
        stop_scheduler(_scheduler)

# ── Helpers ─────────────────────────────────────────────────────────────────
def get_service_id(dt: date):
    dow = dt.weekday()
    if dow == 5: return 'SA'
    if dow == 6: return 'SU'
    return 'WK'

def get_headway(service_id, route_id, stop_id, hour, default=8.0):
    hw_map = {'WK': _headways_wk, 'SA': _headways_sa, 'SU': _headways_su}.get(service_id, _headways_wk)
    return hw_map.get(route_id, {}).get(stop_id, {}).get(hour, default)

# ── Weather code descriptions ────────────────────────────────────────────────
_WEATHER_DESCRIPTIONS = {
    0: 'Clear sky',
    1: 'Mainly clear',
    2: 'Partly cloudy',
    3: 'Overcast',
    45: 'Fog',
    48: 'Icy fog',
    51: 'Light drizzle',
    53: 'Moderate drizzle',
    55: 'Dense drizzle',
    61: 'Slight rain',
    63: 'Moderate rain',
    65: 'Heavy rain',
    80: 'Slight showers',
    81: 'Moderate showers',
    82: 'Violent showers',
    95: 'Thunderstorm',
    96: 'Thunderstorm with hail',
    99: 'Thunderstorm with heavy hail',
}

def _weather_description(code: int) -> str:
    return _WEATHER_DESCRIPTIONS.get(code, 'Unknown')

def _nearest_station(lat: float, lon: float):
    """Return the nearest stop row from _stops_df given a lat/lon pair."""
    if _stops_df is None or lat is None or lon is None:
        return None
    try:
        import math
        best_dist = float('inf')
        best_row = None
        for _, row in _stops_df.iterrows():
            dlat = row['stop_lat'] - lat
            dlon = row['stop_lon'] - lon
            dist = math.sqrt(dlat ** 2 + dlon ** 2)
            if dist < best_dist:
                best_dist = dist
                best_row = row
        return best_row
    except Exception:
        return None

# ── Request / Response models ────────────────────────────────────────────────
class DemandRequest(BaseModel):
    station_id: str
    corridor: Optional[str] = None
    hour: Optional[int] = 9
    date: Optional[str] = None  # YYYY-MM-DD
    weather_code: Optional[Union[int, str]] = 0
    temperature: Optional[float] = 32.0
    event_score: Optional[float] = 0.0

class EventRequest(BaseModel):
    event_name: Optional[str] = 'Special Event'
    event_type: str = 'concert'
    venue_id: Optional[str] = None
    venue_lat: Optional[float] = None
    venue_lon: Optional[float] = None
    venue_capacity: Optional[int] = 10000
    attendance: Optional[int] = 5000
    start_time: str  # ISO datetime e.g. 2026-10-06T19:00:00
    end_time: str
    date: Optional[str] = None

class OptimizeRequest(BaseModel):
    date: Optional[str] = None
    event: Optional[EventRequest] = None
    corridors: Optional[List[str]] = None

class AnomalyRequest(BaseModel):
    station_id: str
    corridor: Optional[str] = None
    hour: int
    observed_count: int
    date: Optional[str] = None

# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get('/stations')
def get_stations():
    """All 57 HMR parent stations with coordinates and corridors."""
    if _station_meta:
        return _station_meta
    stops = _stops_df.to_dict('records')
    for s in stops:
        s['corridors'] = _route_map.get(s['stop_id'], [])
    return stops

@app.get('/corridors')
def get_corridors():
    return [
        {'id': 'RED', 'name': 'Red Line', 'from': 'Miyapur', 'to': 'L. B. Nagar', 'color': '#E31E24'},
        {'id': 'BLUE', 'name': 'Blue Line', 'from': 'Nagole', 'to': 'Raidurg', 'color': '#007ABB'},
        {'id': 'GREEN', 'name': 'Green Line', 'from': 'JBS Parade Ground', 'to': 'MGBS', 'color': '#009846'},
    ]

@app.get('/schedule/current')
def get_current_schedule(corridor: str = 'RED', service: str = 'WK'):
    """Current headways from GTFS for a corridor."""
    hw_map = {'WK': _headways_wk, 'SA': _headways_sa, 'SU': _headways_su}.get(service, _headways_wk)
    corridor_data = hw_map.get(corridor.upper(), {})
    result = []
    for stop_id, hours in corridor_data.items():
        station_row = _stops_df[_stops_df['stop_id'] == stop_id]
        name = station_row['stop_name'].values[0] if len(station_row) > 0 else stop_id
        for hour, hw in sorted(hours.items()):
            result.append({'stop_id': stop_id, 'stop_name': name, 'hour': hour, 'headway_min': hw, 'trains_per_hour': round(60/hw, 1)})
    return result

@app.post('/predict/demand')
def predict_demand(req: DemandRequest):
    """Predict passenger count for a station at a specific hour."""
    corridor = req.corridor
    if not corridor:
        routes = _route_map.get(req.station_id, ['RED']) if _route_map else ['RED']
        corridor = routes[0] if routes else 'RED'
    hour = req.hour if req.hour is not None else 9

    dt = date.fromisoformat(req.date) if req.date else date.today()
    service_id = get_service_id(dt)
    day_of_week = dt.weekday()
    is_weekend = 1 if day_of_week >= 5 else 0
    from utils.features import is_holiday as check_holiday, station_it_density, station_college_density
    holiday = check_holiday(dt)
    it_density = station_it_density(req.station_id)
    college_density = station_college_density(req.station_id)
    trains_ph = round(60 / get_headway(service_id, corridor, req.station_id, hour), 1)
    
    w_code = req.weather_code
    if isinstance(w_code, str):
        w_code = {'clear': 0, 'rain': 1, 'fog': 2}.get(w_code.lower(), 0)
    elif w_code is None:
        w_code = 0

    if _demand_model:
        pred = _demand_model.predict(
            station_id=req.station_id, corridor=corridor, hour=hour,
            day_of_week=day_of_week, is_weekend=is_weekend, is_holiday=holiday,
            trains_per_hour=trains_ph, it_density=it_density, college_density=college_density,
            weather_code=w_code, temperature=req.temperature
        )
    else:
    # Fallback: simple rule-based estimate
        base = {'AME': 35000, 'HTC': 32000, 'MGB': 28000, 'JBS': 22000, 'UPL': 18000}.get(req.station_id, 10000)
        hour_mult = {8: 0.12, 9: 0.11, 17: 0.09, 18: 0.11, 19: 0.10}.get(req.hour, 0.04)
        day_mult = 0.65 if is_weekend else 1.0
        val = int(base * hour_mult * day_mult)
        pred = {'expected': val, 'low': int(val * 0.88), 'high': int(val * 1.12)}
    
    # ── Check for city events affecting this station on target date ─────
    from utils.event_schedule import get_city_events_for_date
    all_events = get_city_events_for_date(dt)
    event_surge_pax = 0
    active_events = []
    
    for ev in all_events:
        nearest = ev.get('nearest_station')
        if not nearest:
            continue
        target_sid = nearest.get('stop_id')
        if target_sid == 'KHR':
            target_sid = 'KHA'
        if target_sid == req.station_id:
            metro_riders = ev.get('metro_riders', 0)
            if metro_riders <= 0:
                continue
            start_str = ev.get('start_time', '19:00:00')
            end_str = ev.get('end_time', '22:00:00')
            try:
                start_h = int(start_str.split('T')[1][:2]) if 'T' in start_str else int(start_str[:2])
                end_h = int(end_str.split('T')[1][:2]) if 'T' in end_str else int(end_str[:2])
            except Exception:
                start_h, end_h = 19, 22

            ingress_hours = [max(5, start_h - 2), max(5, start_h - 1), start_h]
            ingress_weights = {ingress_hours[0]: 0.25, ingress_hours[1]: 0.55, ingress_hours[2]: 0.20}
            
            egress_hours = [end_h, min(23, end_h + 1)]
            egress_weights = {egress_hours[0]: 0.70, egress_hours[1]: 0.30}

            added_pax = 0
            if hour in ingress_weights:
                added_pax = round(metro_riders * ingress_weights[hour] * 0.85)
            elif hour in egress_weights:
                added_pax = round(metro_riders * egress_weights[hour] * 0.90)

            if added_pax > 0:
                event_surge_pax += added_pax
                active_events.append({
                    'name': ev.get('name'),
                    'venue_name': ev.get('venue_name'),
                    'added_passengers': added_pax,
                    'event_type': ev.get('event_type'),
                    'event_url': ev.get('event_url'),
                })

    base_val = pred['expected']
    total_val = base_val + event_surge_pax
    low_val = pred['low'] + event_surge_pax
    high_val = pred['high'] + event_surge_pax

    return {
        'station_id': req.station_id,
        'corridor': corridor,
        'hour': hour,
        'date': str(dt),
        'service_type': service_id,
        'baseline_passengers': base_val,
        'event_surge': event_surge_pax,
        'expected_passengers': total_val,
        'confidence_low': low_val,
        'confidence_high': high_val,
        'active_events': active_events,
        'trains_per_hour': trains_ph,
        'current_headway_min': get_headway(service_id, corridor, req.station_id, hour)
    }

@app.post('/predict/event')
def predict_event(req: EventRequest):
    """Calculate impact of an event on all nearby stations."""
    venue_lat = req.venue_lat
    venue_lon = req.venue_lon
    venue_cap = req.venue_capacity
    
    if req.venue_id:
        venues = get_venues()
        v = next((x for x in venues if x['id'] == req.venue_id), None)
        if v:
            venue_lat = v['lat']; venue_lon = v['lon']; venue_cap = v['capacity']
    
    if venue_lat is None or venue_lon is None:
        raise HTTPException(400, 'Provide venue_id or venue_lat/venue_lon')
    
    start_dt = datetime.fromisoformat(req.start_time)
    start_hour = start_dt.hour
    end_dt = datetime.fromisoformat(req.end_time)
    end_hour = end_dt.hour
    
    # Build base demands (simple lookup or model)
    base_demands = {}
    dt = date.fromisoformat(req.date) if req.date else start_dt.date()
    service_id = get_service_id(dt)
    for _, station in _stops_df.iterrows():
        sid = station['stop_id']
        routes = _route_map.get(sid, ['RED'])
        route = routes[0] if routes else 'RED'
        base_demands[sid] = {}
        for h in range(5, 24):
            base = {'AME': 35000, 'HTC': 32000, 'MGB': 28000, 'JBS': 22000, 'UPL': 18000}.get(sid, 8000)
            hour_mult = {5:0.01,6:0.03,7:0.06,8:0.12,9:0.11,10:0.07,11:0.05,12:0.05,13:0.05,14:0.04,15:0.04,16:0.06,17:0.09,18:0.11,19:0.10,20:0.07,21:0.04,22:0.02,23:0.01}.get(h, 0.03)
            base_demands[sid][h] = round(base * hour_mult)
    
    impact = calculate_event_impact(
        event_type=req.event_type,
        venue_lat=venue_lat, venue_lon=venue_lon,
        attendance=req.attendance, venue_capacity=venue_cap,
        start_hour=start_hour, end_hour=end_hour,
        base_demands=base_demands
    )
    
    ranked = rank_stations_by_impact(impact)
    
    # Enrich with station names
    for item in ranked:
        row = _stops_df[_stops_df['stop_id'] == item['station_id']]
        item['station_name'] = row['stop_name'].values[0] if len(row) > 0 else item['station_id']
        item['corridors'] = _route_map.get(item['station_id'], [])
    
    # Build hourly surge table for top stations
    hourly_table = {}
    for item in ranked[:5]:
        sid = item['station_id']
        if sid in impact:
            hourly_table[sid] = {str(h): v for h, v in impact[sid].items()}
    
    return {
        'event': req.dict(),
        'top_impacted_stations': ranked,
        'hourly_impact': hourly_table,
        'total_stations_impacted': len(impact)
    }

@app.post('/optimize')
def optimize_frequency(req: OptimizeRequest):
    """Optimize train frequencies for a given date, optionally with an event."""
    dt = date.fromisoformat(req.date) if req.date else date.today()
    service_id = get_service_id(dt)
    corridors = req.corridors or ['RED', 'BLUE', 'GREEN']
    
    # Build base demand
    from utils.features import station_it_density, station_college_density, is_holiday as check_holiday
    day_of_week = dt.weekday()
    is_weekend = day_of_week >= 5
    holiday = check_holiday(dt)
    
    demand = {}
    base_demand = {}
    for _, station in _stops_df.iterrows():
        sid = station['stop_id']
        demand[sid] = {}
        base_demand[sid] = {}
        base = {'AME': 35000, 'HTC': 32000, 'MGB': 28000, 'JBS': 22000, 'UPL': 18000, 'RDG': 20000, 'MYP': 15000, 'LBN': 15000, 'NAG': 12000}.get(sid, 8000)
        day_mult = 0.60 if day_of_week == 6 else (0.72 if day_of_week == 5 else 1.0)
        for h in range(5, 24):
            hour_mult = {5:0.01,6:0.03,7:0.06,8:0.12,9:0.11,10:0.07,11:0.05,12:0.05,13:0.05,14:0.04,15:0.04,16:0.06,17:0.09,18:0.11,19:0.10,20:0.07,21:0.04,22:0.02,23:0.01}.get(h, 0.03)
            val = round(base * hour_mult * day_mult)
            demand[sid][h] = val
            base_demand[sid][h] = val
    
    # Apply event impact if provided
    if req.event:
        ev = req.event
        venue_lat, venue_lon, venue_cap = ev.venue_lat, ev.venue_lon, ev.venue_capacity
        if ev.venue_id:
            vv = next((x for x in get_venues() if x['id'] == ev.venue_id), None)
            if vv:
                venue_lat, venue_lon, venue_cap = vv['lat'], vv['lon'], vv['capacity']
        if venue_lat and venue_lon:
            start_hour = datetime.fromisoformat(ev.start_time).hour
            end_hour = datetime.fromisoformat(ev.end_time).hour
            impact = calculate_event_impact(ev.event_type, venue_lat, venue_lon,
                                            ev.attendance, venue_cap, start_hour, end_hour, demand)
            for sid, hours in impact.items():
                for h, vals in hours.items():
                    demand[sid][h] = vals['total_demand']
    
    # Get current schedule from GTFS as baseline
    hw_map = {'WK': _headways_wk, 'SA': _headways_sa, 'SU': _headways_su}.get(service_id, _headways_wk)
    
    # Run optimizer
    corridor_stations = {'RED': [], 'BLUE': [], 'GREEN': []}
    for sid, routes in _route_map.items():
        for r in routes:
            if r in corridor_stations and sid not in corridor_stations[r]:
                corridor_stations[r].append(sid)
    
    recommended = optimize_schedule(
        demand,
        corridors=corridors,
        corridor_stations=corridor_stations,
        baseline_headways=hw_map,
        base_demand_by_station_hour=base_demand
    )
    
    # Build comparison: current vs recommended for a sample station per corridor
    sample_stations = {'RED': 'AME', 'BLUE': 'HTC', 'GREEN': 'MGB'}
    comparison = {}
    for corridor in corridors:
        sample = sample_stations.get(corridor, '')
        comparison[corridor] = []
        for hour in range(5, 24):
            current_hw = hw_map.get(corridor, {}).get(sample, {}).get(hour, 8.0)
            rec = recommended.get(corridor, {}).get(hour, {})
            comparison[corridor].append({
                'hour': hour,
                'current_headway_min': current_hw,
                'current_tph': round(60/current_hw, 1) if current_hw else 0,
                'recommended_headway_min': rec.get('headway_min', current_hw),
                'recommended_tph': rec.get('trains_per_hour', 0),
                'max_demand': rec.get('max_station_demand', 0),
                'fleet_constrained': rec.get('fleet_constrained', False)
            })
    
    return {
        'date': str(dt),
        'service_type': service_id,
        'corridors_optimized': corridors,
        'schedule': recommended,
        'comparison': comparison,
        'has_event': req.event is not None
    }

@app.get('/venues')
def list_venues():
    return get_venues()

@app.get('/')
def root():
    return {
        'status': 'online',
        'service': 'MetroMind Transit Demand & Headway Optimization API',
        'version': '2.0.0',
        'health': '/health',
        'docs': '/docs'
    }

@app.get('/health')
def health():
    return {'status': 'ok', 'model_loaded': _demand_model is not None}

# ── NEW: Live Weather endpoint ────────────────────────────────────────────────

@app.get('/weather/live')
@app.get('/weather/current')
def get_live_weather():
    """
    Return the most recently cached weather data for Hyderabad.

    The cache is refreshed every 3 hours by the background scheduler.
    ``is_stale=true`` if the cache is older than 3 hours or missing.
    """
    from scheduler.background_worker import WeatherCache
    cached = WeatherCache.load()
    return {
        'weather_code': cached['weather_code'],
        'temperature': cached['temperature'],
        'description': _weather_description(cached['weather_code']),
        'timestamp': cached['timestamp'],
        'is_stale': cached['is_stale'],
        'forecast': cached['forecast'],
    }

# ── NEW: Live Events endpoints ────────────────────────────────────────────────

@app.post('/events/refresh')
def refresh_events():
    """Trigger an immediate live re-scrape of city events across Hyderabad."""
    from scheduler.background_worker import job_scrape_events, EventCache
    job_scrape_events()
    events = EventCache.load()
    return {'status': 'refreshed', 'total_events': len(events), 'timestamp': datetime.now().isoformat()}

@app.get('/events/live')
def get_live_events(within_hours: int = 48):
    """
    Return upcoming events from the live events cache, enriched with the
    nearest HMR metro station for each event venue.

    Query Parameters
    ----------------
    within_hours : int
        Only include events starting within the next N hours (default 48).
    """
    from scheduler.background_worker import EventCache
    events = EventCache.get_upcoming(within_hours=within_hours)
    enriched = []
    for ev in events:
        item = dict(ev)
        nearest = _nearest_station(ev.get('venue_lat'), ev.get('venue_lon'))
        if nearest is not None:
            item['nearest_station'] = {
                'stop_id': nearest['stop_id'],
                'stop_name': nearest['stop_name'],
                'corridors': _route_map.get(nearest['stop_id'], []),
            }
        enriched.append(item)
    return {'count': len(enriched), 'within_hours': within_hours, 'events': enriched}

@app.get('/events/active')
def get_active_events():
    """
    Return events that are currently ongoing or starting within the next
    60 minutes, enriched with nearest HMR station info.
    """
    from scheduler.background_worker import EventCache
    events = EventCache.get_active_now(buffer_minutes=60)
    enriched = []
    for ev in events:
        item = dict(ev)
        nearest = _nearest_station(ev.get('venue_lat'), ev.get('venue_lon'))
        if nearest is not None:
            item['nearest_station'] = {
                'stop_id': nearest['stop_id'],
                'stop_name': nearest['stop_name'],
                'corridors': _route_map.get(nearest['stop_id'], []),
            }
        enriched.append(item)
    return {'count': len(enriched), 'events': enriched}

# ── NEW: Demand prediction with live data ─────────────────────────────────────

@app.post('/predict/demand-with-live-data')
def predict_demand_with_live_data(req: DemandRequest):
    """
    Same as ``POST /predict/demand`` but auto-enriches weather and event context
    from live caches before running the model.

    * Weather is taken from WeatherCache unless the caller explicitly provides
      non-default values (weather_code != 0 or temperature != 32.0).
    * Active events near the requested station are automatically detected and
      their event_score is injected if the caller did not supply one.

    Returns the same fields as ``/predict/demand`` plus:
        live_data_used : dict describing which live sources were applied.
    """
    from scheduler.background_worker import WeatherCache, EventCache

    live_data_used = {
        'weather_source': 'request',
        'weather_code_source': 'caller',
        'active_events': [],
    }

    # ── Weather enrichment ──────────────────────────────────────────────
    caller_weather_code = req.weather_code
    caller_temperature = req.temperature
    # Treat the model defaults (0 and 32.0) as "not explicitly set"
    weather_is_default = (
        (caller_weather_code == 0 or caller_weather_code is None)
        and (caller_temperature is None or abs((caller_temperature or 32.0) - 32.0) < 0.01)
    )

    if weather_is_default:
        cached = WeatherCache.load()
        if not cached['is_stale']:
            # Use forecast slot that matches the requested hour
            fc_code, fc_temp = WeatherCache.get_weather_for_hour(req.hour)
            req = req.copy(update={'weather_code': fc_code, 'temperature': fc_temp})
            live_data_used['weather_source'] = 'live'
            live_data_used['weather_code_source'] = 'weather_cache'
        else:
            live_data_used['weather_source'] = 'cache_stale'
            live_data_used['weather_code_source'] = 'default'

    # ── Active event enrichment ─────────────────────────────────────────
    if req.event_score == 0.0 or req.event_score is None:
        active_events = EventCache.get_active_now(buffer_minutes=60)
        if active_events:
            # Use the maximum event score across all active events as a proxy
            max_score = max(
                ev.get('event_score', ev.get('surge_factor', 0.3))
                for ev in active_events
            )
            req = req.copy(update={'event_score': float(max_score)})
            live_data_used['active_events'] = [
                {k: v for k, v in ev.items() if k in ('name', 'start_time', 'end_time', 'event_type')}
                for ev in active_events
            ]

    # ── Delegate to core prediction logic ──────────────────────────────
    result = predict_demand(req)
    result['live_data_used'] = live_data_used
    return result

# ── NEW: Directional demand prediction ───────────────────────────────────────

@app.post('/predict/directional')
def predict_directional(req: DemandRequest):
    """
    Directional demand prediction – splits total passengers into inbound and
    outbound flows for the given station, corridor, and hour.

    Returns
    -------
    station_id, corridor, hour, total_passengers, inbound, outbound,
    inbound_direction, outbound_direction, peak_type, inbound_fraction,
    asymmetry_ratio
    """
    if _directional_model is None:
        raise HTTPException(503, 'Directional model not loaded. Run train_model.py first.')

    corridor = req.corridor
    if not corridor:
        routes = _route_map.get(req.station_id, ['RED']) if _route_map else ['RED']
        corridor = routes[0] if routes else 'RED'
    hour = req.hour if req.hour is not None else 9

    dt = date.fromisoformat(req.date) if req.date else date.today()
    service_id = get_service_id(dt)
    day_of_week = dt.weekday()
    is_weekend = 1 if day_of_week >= 5 else 0

    from utils.features import is_holiday as check_holiday, station_it_density, station_college_density
    holiday = check_holiday(dt)
    it_density = station_it_density(req.station_id)
    college_density = station_college_density(req.station_id)
    trains_ph = int(round(60 / get_headway(service_id, corridor, req.station_id, hour)))

    w_code = req.weather_code
    if isinstance(w_code, str):
        w_code = {'clear': 0, 'rain': 1, 'fog': 2}.get(w_code.lower(), 0)
    elif w_code is None:
        w_code = 0

    result = _directional_model.predict_directional(
        station_id=req.station_id,
        corridor=corridor,
        hour=hour,
        day_of_week=day_of_week,
        is_weekend=bool(is_weekend),
        is_holiday=bool(holiday),
        trains_per_hour=trains_ph,
        it_density=it_density,
        college_density=college_density,
        weather_code=w_code,
        temperature=req.temperature or 32.0,
        base_model=_demand_model,
    )

    return {
        'station_id': req.station_id,
        'corridor': corridor,
        'hour': hour,
        'total_passengers': result.get('total', 0),
        'inbound': result.get('inbound', 0),
        'outbound': result.get('outbound', 0),
        'inbound_direction': result.get('inbound_direction', ''),
        'outbound_direction': result.get('outbound_direction', ''),
        'peak_type': result.get('peak_type', 'off_peak'),
        'inbound_fraction': result.get('inbound_fraction', 0.5),
        'asymmetry_ratio': result.get('asymmetry_ratio', 1.0),
    }

# ── NEW: Anomaly detection endpoints ─────────────────────────────────────────

@app.get('/anomalies/active')
def get_active_anomalies():
    """
    Return the current list of CRITICAL / HIGH severity anomaly alerts
    generated by the background detector, sorted critical-first.

    Returns an empty list if the alerts file does not exist yet.
    """
    if not ACTIVE_ALERTS_PATH.exists():
        return {'count': 0, 'alerts': []}
    try:
        with ACTIVE_ALERTS_PATH.open(encoding='utf-8') as fh:
            alerts = json.load(fh)
    except Exception:
        return {'count': 0, 'alerts': []}

    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    alerts_sorted = sorted(
        alerts,
        key=lambda a: severity_order.get(a.get('severity', 'LOW'), 4)
    )
    return {'count': len(alerts_sorted), 'alerts': alerts_sorted}

@app.post('/anomalies/detect')
def detect_anomaly(req: AnomalyRequest):
    """
    On-demand anomaly detection for a specific station/hour.

    Computes expected demand via the demand model (or rule-based fallback),
    then runs the anomaly detector and returns a full detection result.
    """
    if _anomaly_detector is None:
        raise HTTPException(503, 'Anomaly detector not loaded.')

    dt = date.fromisoformat(req.date) if req.date else date.today()
    service_id = get_service_id(dt)
    day_of_week = dt.weekday()
    is_weekend = 1 if day_of_week >= 5 else 0

    corridor = req.corridor
    if not corridor:
        routes = _route_map.get(req.station_id, ['RED']) if _route_map else ['RED']
        corridor = routes[0] if routes else 'RED'

    # ── Compute expected count ──────────────────────────────────────────
    from utils.features import is_holiday as check_holiday, station_it_density, station_college_density
    holiday = check_holiday(dt)
    trains_ph = round(60 / get_headway(service_id, corridor, req.station_id, req.hour), 1)

    if _demand_model:
        try:
            pred = _demand_model.predict(
                station_id=req.station_id, corridor=corridor, hour=req.hour,
                day_of_week=day_of_week, is_weekend=is_weekend, is_holiday=holiday,
                trains_per_hour=trains_ph,
                it_density=station_it_density(req.station_id),
                college_density=station_college_density(req.station_id),
                weather_code=0, temperature=32.0,
            )
            expected = pred['expected']
        except Exception:
            expected = None
    else:
        base = {'AME': 35000, 'HTC': 32000, 'MGB': 28000, 'JBS': 22000, 'UPL': 18000}.get(req.station_id, 10000)
        hour_mult = {8: 0.12, 9: 0.11, 17: 0.09, 18: 0.11, 19: 0.10}.get(req.hour, 0.04)
        day_mult = 0.65 if is_weekend else 1.0
        expected = int(base * hour_mult * day_mult)

    result = _anomaly_detector.detect(
        station_id=req.station_id,
        corridor=corridor,
        hour=req.hour,
        day_of_week=day_of_week,
        observed_count=req.observed_count,
        expected_count=expected or req.observed_count,
    )
    result['date'] = str(dt)
    result['station_id'] = req.station_id
    result['corridor'] = corridor
    result['hour'] = req.hour
    result['observed_count'] = req.observed_count
    result['expected_count'] = expected
    return result

# ── NEW: Scheduler status endpoint ───────────────────────────────────────────

@app.get('/scheduler/status')
def scheduler_status():
    """
    Return the current status of the background scheduler and its jobs,
    together with high-level data freshness indicators.
    """
    from scheduler.background_worker import WeatherCache, EventCache, get_scheduler

    scheduler = get_scheduler()
    scheduler_running = scheduler is not None and scheduler.running

    jobs_info = []
    if scheduler_running:
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            jobs_info.append({
                'id': job.id,
                'name': job.name,
                'next_run': next_run.isoformat() if next_run else None,
            })

    # Weather freshness
    weather_cached = WeatherCache.load()
    last_weather_update = weather_cached.get('timestamp')

    # Live event count
    live_events_count = len(EventCache.load())

    # Active alert count
    active_alerts_count = 0
    if ACTIVE_ALERTS_PATH.exists():
        try:
            with ACTIVE_ALERTS_PATH.open(encoding='utf-8') as fh:
                active_alerts_count = len(json.load(fh))
        except Exception:
            pass

    return {
        'scheduler_running': scheduler_running,
        'jobs': jobs_info,
        'last_weather_update': last_weather_update,
        'weather_is_stale': weather_cached.get('is_stale', True),
        'live_events_count': live_events_count,
        'active_alerts_count': active_alerts_count,
    }

# ── NEW: Autonomous Auto-Optimize endpoint ───────────────────────────────────

# Metro ridership fractions: what % of event attendees actually use metro
# Based on Hyderabad Metro ridership studies - most attendees drive or use buses
METRO_RIDERSHIP_FRACTIONS = {
    'cricket_international': 0.22,  # ~22% of cricket fans use metro
    'cricket_ipl': 0.20,
    'concert': 0.18,
    'tech_summit': 0.30,            # tech workers more likely to use metro
    'ganesh_procession': 0.12,      # processions are spread across city
    'exhibition': 0.25,
    'political_rally': 0.08,        # rallies often have buses organized
    'college_fest': 0.35,           # students heavily use metro
    'football': 0.18,
    'other': 0.15,
}

MANUAL_EVENTS_FILE = Path(__file__).resolve().parent / 'data' / 'manual_events.json'

def _load_manual_events() -> List[Dict[str, Any]]:
    if not MANUAL_EVENTS_FILE.exists():
        return []
    try:
        with open(MANUAL_EVENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _save_manual_events(events: List[Dict[str, Any]]) -> None:
    MANUAL_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MANUAL_EVENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(events, f, indent=2)

class ManualEventCreateRequest(BaseModel):
    name: str
    event_type: str = 'other'
    venue_name: Optional[str] = None
    venue_id: Optional[str] = None
    venue_lat: Optional[float] = None
    venue_lon: Optional[float] = None
    nearest_stop_id: Optional[str] = None
    distance_to_nearest_metro_km: Optional[float] = None
    date: str  # YYYY-MM-DD
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    venue_capacity: Optional[int] = None
    ticket_price_avg: Optional[float] = None
    user_interest_hearts: Optional[int] = None
    event_url: Optional[str] = None

@app.get('/manual-events')
def get_manual_events(date: Optional[str] = None):
    all_evs = _load_manual_events()
    if date:
        return [e for e in all_evs if e.get('date') == date or (e.get('start_time', '')[:10] == date)]
    return all_evs

@app.post('/manual-events')
def create_manual_event(req: ManualEventCreateRequest):
    all_evs = _load_manual_events()
    import uuid
    ev_id = f"man_{uuid.uuid4().hex[:8]}"

    s_time = req.start_time or f"{req.date}T19:00:00"
    if 'T' not in s_time:
        s_time = f"{req.date}T{s_time}:00" if len(s_time) == 5 else f"{req.date}T{s_time}"
    e_time = req.end_time or f"{req.date}T22:30:00"
    if 'T' not in e_time:
        e_time = f"{req.date}T{e_time}:00" if len(e_time) == 5 else f"{req.date}T{e_time}"

    url = req.event_url
    if not url:
        url = f"https://in.bookmyshow.com/explore/events-hyderabad?search={urllib.parse.quote_plus(req.name)}"

    item = {
        'id': ev_id,
        'name': req.name,
        'event_type': req.event_type,
        'venue_name': req.venue_name or 'Hyderabad Venue',
        'venue_id': req.venue_id or 'custom_venue',
        'venue_lat': req.venue_lat or 17.4063,
        'venue_lon': req.venue_lon or 78.5480,
        'nearest_stop_id': req.nearest_stop_id,
        'distance_to_nearest_metro_km': req.distance_to_nearest_metro_km,
        'date': req.date,
        'start_time': s_time,
        'end_time': e_time,
        'venue_capacity': req.venue_capacity or 15000,
        'ticket_price_avg': req.ticket_price_avg or 600.0,
        'user_interest_hearts': req.user_interest_hearts or 12000,
        'event_url': url,
        'is_manual': True,
        'created_at': datetime.now().isoformat(),
    }
    all_evs.append(item)
    _save_manual_events(all_evs)
    return {'status': 'success', 'event': item}

@app.delete('/manual-events/{event_id}')
def delete_manual_event(event_id: str):
    all_evs = _load_manual_events()
    filtered = [e for e in all_evs if str(e.get('id')) != str(event_id) and e.get('name') != event_id]
    _save_manual_events(filtered)
    return {'status': 'success', 'deleted_id': event_id, 'remaining_count': len(filtered)}

class AutoOptimizeRequest(BaseModel):
    exclude_event_ids: Optional[List[str]] = None
    date: Optional[str] = None
    corridors: Optional[List[str]] = None
    custom_events: Optional[List[Dict[str, Any]]] = None

@app.post('/auto-optimize')
def auto_optimize(req: AutoOptimizeRequest = None):
    """
    Fully autonomous optimization pipeline.
    
    1. Automatically detects city events across Hyderabad for the selected date.
    2. Integrates live or forecasted weather (including rain commuter surge).
    3. Calculates realistic crowd surge for event ingress and egress windows.
    4. Computes directional headways (Inbound vs Outbound) based on crowd flow.
    5. Allows transit operators to exclude specific events and recalculates instantly.
    """
    from utils.event_schedule import (
        get_city_events_for_date,
        get_weather_for_date,
        METRO_RIDERSHIP_FRACTIONS
    )
    from models.optimizer import optimize_schedule, FLEET_SIZE, trains_needed
    from utils.holiday_schedule import (
        get_holiday_and_weekend_details,
        INTERCITY_BUS_AND_RAIL_STATIONS,
        TOURIST_RECREATION_STATIONS
    )
    import math

    global _stops_df, _route_map, _headways_wk, _headways_sa, _headways_su
    if _stops_df is None:
        from gtfs.loader import load_stops, get_station_route_map
        from gtfs.headway import get_headway_dict
        _stops_df = load_stops()
        _route_map = get_station_route_map()
        _headways_wk = get_headway_dict('WK')
        _headways_sa = get_headway_dict('SA')
        _headways_su = get_headway_dict('SU')

    if req is None:
        req = AutoOptimizeRequest()

    dt = date.fromisoformat(req.date) if req.date else date.today()
    service_id = get_service_id(dt)
    day_of_week = dt.weekday()
    is_weekend = day_of_week >= 5
    corridors = req.corridors or ['RED', 'BLUE', 'GREEN']
    exclude_ids = set(req.exclude_event_ids or [])

    # ── 0. Public Holiday & Long Weekend Analysis ────────────────────────
    holiday_info = get_holiday_and_weekend_details(dt)

    # ── 1. Fetch weather for target date ─────────────────────────────────
    weather_info = get_weather_for_date(dt)
    weather_code = weather_info.get('weather_code', 0)
    temperature = weather_info.get('temperature', 30.0)
    is_rain = weather_info.get('is_rain', False)
    rain_surge = weather_info.get('rain_surge_multiplier', 1.0)

    # ── 2. Fetch events for target date ──────────────────────────────────
    all_events = get_city_events_for_date(dt)

    # Ingest one-off custom_events from request payload if passed
    if req.custom_events:
        for ce in req.custom_events:
            ce_id = str(ce.get('id', ce.get('name', '')))
            if not any(str(e.get('id', e.get('name', ''))) == ce_id for e in all_events):
                all_events.append(ce)

    events_used = []
    events_excluded = []
    for ev in all_events:
        ev_id = str(ev.get('id', ev.get('name', '')))
        ev_name = ev.get('name', '')
        if ev_id in exclude_ids or ev_name in exclude_ids:
            events_excluded.append({
                'id': ev_id,
                'name': ev_name,
                'event_type': ev.get('event_type', 'other'),
                'excluded': True,
            })
            continue

        events_used.append(ev)

    # ── 3. Build baseline passenger demand ───────────────────────────────
    demand = {}
    base_demand = {}
    for _, station in _stops_df.iterrows():
        sid = station['stop_id']
        demand[sid] = {}
        base_demand[sid] = {}
        
        base_pax = {
            'AME': 35000, 'HTC': 32000, 'MGB': 28000, 'JBS': 22000,
            'UPL': 18000, 'RDG': 20000, 'MYP': 16000, 'LBN': 16000, 'NAG': 13000
        }.get(sid, 9000)
        
        if holiday_info['is_holiday']:
            day_mult = 0.70
        elif day_of_week == 6:
            day_mult = 0.65
        elif day_of_week == 5:
            day_mult = 0.75
        else:
            day_mult = 1.0

        for h in range(5, 24):
            # Hourly distribution profile
            hour_mult = {
                5: 0.015, 6: 0.035, 7: 0.065, 8: 0.115, 9: 0.125,
                10: 0.075, 11: 0.050, 12: 0.050, 13: 0.045, 14: 0.045,
                15: 0.055, 16: 0.075, 17: 0.095, 18: 0.120, 19: 0.110,
                20: 0.075, 21: 0.050, 22: 0.030, 23: 0.015
            }.get(h, 0.035)

            val = round(base_pax * hour_mult * day_mult)

            # ── A. Holiday & Long Weekend Intercity Bus Hub Morning Exodus Surge ──
            # Commuters heading to MGBS, JBS, LB Nagar, Miyapur, Secunderabad to catch intercity buses/trains
            if (holiday_info['is_holiday'] or holiday_info['is_long_weekend']) and sid in INTERCITY_BUS_AND_RAIL_STATIONS:
                if 6 <= h <= 11:
                    bus_mult = 1.55 if holiday_info.get('holiday_type') == 'festival_mass_exodus' else 1.40
                    val = round(val * bus_mult)
                elif holiday_info.get('long_weekend_position') in ['end', 'return'] and 17 <= h <= 22:
                    val = round(val * 1.40)

            # ── B. Holiday & Long Weekend Tourist, Lake & Leisure Spots Surge ──
            # Heavy family and tourist leisure crowds at Hussain Sagar/Tank Bund, Durgam Cheruvu, Shilparamam, etc.
            if (holiday_info['is_holiday'] or holiday_info['is_long_weekend'] or is_weekend) and sid in TOURIST_RECREATION_STATIONS:
                if 13 <= h <= 21:
                    tourist_mult = 1.50 if sid in ['KHA', 'DGC'] else 1.35
                    val = round(val * tourist_mult)

            # ── C. Corporate IT Corridor Office Drop on Public Holidays ──
            if holiday_info['is_holiday'] and sid in ['RDG', 'MAD'] and not is_weekend:
                val = round(val * 0.50)

            base_demand[sid][h] = val

            # Apply rain commuter surge across the network if applicable
            if is_rain:
                val = round(val * rain_surge)

            demand[sid][h] = val

    # ── 4. Apply Event Ingress & Egress Surges ────────────────────────────
    # Tracks event-induced directional pressure per corridor and hour
    # structure: {corridor: {hour: {'inbound_boost': float, 'outbound_boost': float}}}
    corridor_event_bias = {c: {h: {'inbound_boost': 0.0, 'outbound_boost': 0.0} for h in range(5, 24)} for c in corridors}

    for ev in events_used:
        metro_riders = ev.get('metro_riders', 0)
        nearest = ev.get('nearest_station')
        if not nearest or metro_riders <= 0:
            continue

        target_sid = nearest['stop_id']
        if target_sid == 'KHR':
            target_sid = 'KHA'
        ev_corridors = nearest.get('corridors', ['BLUE'])
        primary_corridor = ev_corridors[0] if ev_corridors else 'BLUE'

        # Extract start & end hours in local time
        start_str = ev.get('start_time', '19:00:00')
        end_str = ev.get('end_time', '22:00:00')
        try:
            start_h = int(start_str.split('T')[1][:2]) if 'T' in start_str else int(start_str[:2])
            end_h = int(end_str.split('T')[1][:2]) if 'T' in end_str else int(end_str[:2])
        except Exception:
            start_h = 19
            end_h = 22

        # Ingress Surge (2 hours prior up to start): Crowds heading TO venue
        ingress_hours = [max(5, start_h - 2), max(5, start_h - 1), start_h]
        ingress_weights = {ingress_hours[0]: 0.25, ingress_hours[1]: 0.55, ingress_hours[2]: 0.20}
        
        for ih in ingress_hours:
            if ih in demand.get(target_sid, {}):
                added = round(metro_riders * ingress_weights.get(ih, 0.3) * 0.85)
                demand[target_sid][ih] += added

                # Directional bias: people traveling TOWARDS the venue
                # Uppal on Blue: inbound (Raidurg -> Nagole)
                # HITEC/Raidurg on Blue: outbound (Nagole -> Raidurg)
                # Central Red: inbound (from outer terminals)
                if primary_corridor in corridor_event_bias and ih in corridor_event_bias[primary_corridor]:
                    if target_sid in ['UPL', 'STD', 'NAG']:
                        corridor_event_bias[primary_corridor][ih]['inbound_boost'] += 0.30
                    elif target_sid in ['HTC', 'RDG', 'DGC', 'MAD']:
                        corridor_event_bias[primary_corridor][ih]['outbound_boost'] += 0.30
                    elif target_sid in ['KHA', 'ASM', 'LKP', 'KHR']:
                        corridor_event_bias[primary_corridor][ih]['inbound_boost'] += 0.30
                    else:
                        corridor_event_bias[primary_corridor][ih]['inbound_boost'] += 0.20

        # Egress Surge (event end and subsequent hour): Crowds leaving venue
        egress_hours = [end_h, min(23, end_h + 1)]
        egress_weights = {egress_hours[0]: 0.70, egress_hours[1]: 0.30}

        for eh in egress_hours:
            if eh in demand.get(target_sid, {}):
                added = round(metro_riders * egress_weights.get(eh, 0.5) * 0.90)
                demand[target_sid][eh] += added

                # Directional bias: people traveling AWAY from the venue
                if primary_corridor in corridor_event_bias and eh in corridor_event_bias[primary_corridor]:
                    if target_sid in ['UPL', 'STD', 'NAG']:
                        corridor_event_bias[primary_corridor][eh]['outbound_boost'] += 0.35
                    elif target_sid in ['HTC', 'RDG', 'DGC', 'MAD']:
                        corridor_event_bias[primary_corridor][eh]['inbound_boost'] += 0.35
                    elif target_sid in ['KHA', 'ASM', 'LKP', 'KHR']:
                        corridor_event_bias[primary_corridor][eh]['outbound_boost'] += 0.35
                    else:
                        corridor_event_bias[primary_corridor][eh]['outbound_boost'] += 0.20

    # ── 5. Build corridor station map ────────────────────────────────────
    corridor_stations = {'RED': [], 'BLUE': [], 'GREEN': []}
    for sid, routes in _route_map.items():
        for r in routes:
            if r in corridor_stations and sid not in corridor_stations[r]:
                corridor_stations[r].append(sid)

    # ── 6. Baseline GTFS headways ────────────────────────────────────────
    hw_map = {'WK': _headways_wk, 'SA': _headways_sa, 'SU': _headways_su}.get(service_id, _headways_wk)

    # ── 7. Run optimization engine ───────────────────────────────────────
    recommended = optimize_schedule(
        demand,
        corridors=corridors,
        corridor_stations=corridor_stations,
        baseline_headways=hw_map,
        base_demand_by_station_hour=base_demand,
    )

    # ── 8. Compute directional headways (Inbound vs Outbound) ────────────
    directional_headways = {}
    for corridor in corridors:
        corridor_hours = []
        for hour in range(5, 24):
            rec = recommended.get(corridor, {}).get(hour, {})
            headway = rec.get('headway_min', 8.0)
            baseline_hw = rec.get('baseline_headway_min', 8.0)
            fleet_trains = rec.get('fleet_trains', 0)
            fleet_constrained = rec.get('fleet_constrained', False)
            max_demand = rec.get('max_station_demand', 0)

            # Base directional split: morning vs evening commuter rules
            is_peak = (6 <= hour <= 10) or (16 <= hour <= 21)
            if 6 <= hour <= 10:  # Morning peak
                if corridor == 'RED':
                    inbound_frac, outbound_frac = 0.70, 0.30
                elif corridor == 'BLUE':
                    # Commuters enter IT corridor: Nagole -> Raidurg (outbound) is heavy
                    inbound_frac, outbound_frac = 0.30, 0.70
                else:
                    inbound_frac, outbound_frac = 0.55, 0.45
            elif 16 <= hour <= 21:  # Evening peak (starts at 16:00 / 4 PM)
                if corridor == 'RED':
                    inbound_frac, outbound_frac = 0.35, 0.65
                elif corridor == 'BLUE':
                    # IT workers leave HITEC City/Raidurg: Raidurg -> Nagole (inbound) is heavy
                    inbound_frac, outbound_frac = 0.70, 0.30
                else:
                    inbound_frac, outbound_frac = 0.45, 0.55
            else:  # Off-peak
                inbound_frac, outbound_frac = 0.50, 0.50

            # Apply event directional bias if an event surge occurs at this hour
            bias = corridor_event_bias.get(corridor, {}).get(hour, {})
            in_boost = bias.get('inbound_boost', 0.0)
            out_boost = bias.get('outbound_boost', 0.0)

            if in_boost > 0 and out_boost > 0:
                inbound_frac, outbound_frac = 0.50, 0.50
            elif in_boost > 0:
                min_out = 0.35 if is_peak else 0.20
                inbound_frac = min(1.0 - min_out, inbound_frac + in_boost)
                outbound_frac = 1.0 - inbound_frac
            elif out_boost > 0:
                min_in = 0.35 if is_peak else 0.20
                outbound_frac = min(1.0 - min_in, outbound_frac + out_boost)
                inbound_frac = 1.0 - outbound_frac

            # Compute directional headways (tighter for the dominant flow)
            inbound_headway = round(headway / (2 * inbound_frac), 1) if inbound_frac > 0 else headway
            outbound_headway = round(headway / (2 * outbound_frac), 1) if outbound_frac > 0 else headway

            # Bounds clamping: safety minimum 2.0 min, peak-hour ceiling 6.0 min (15.0 min off-peak)
            max_hw = 6.0 if is_peak else 15.0
            inbound_headway = max(2.0, min(max_hw, inbound_headway))
            outbound_headway = max(2.0, min(max_hw, outbound_headway))

            corridor_hours.append({
                'hour': hour,
                'baseline_headway': baseline_hw,
                'recommended_headway': headway,
                'inbound_headway': inbound_headway,
                'outbound_headway': outbound_headway,
                'inbound_fraction': round(inbound_frac, 2),
                'outbound_fraction': round(outbound_frac, 2),
                'inbound_tph': round(60 / inbound_headway, 1),
                'outbound_tph': round(60 / outbound_headway, 1),
                'max_demand': max_demand,
                'fleet_trains': fleet_trains,
                'fleet_constrained': False,
            })
        directional_headways[corridor] = corridor_hours

    # ── 9. Generate AI Dispatch Recommendations ──────────────────────────
    recommendations = []

    # Weather alert card
    if is_rain:
        recommendations.append({
            'severity': 'warning',
            'corridor': 'NETWORK-WIDE',
            'message': f"Weather Alert: {weather_info.get('description', 'Rain')} ({temperature}°C). Road waterlogging and congestion causing estimated +{int((rain_surge-1)*100)}% commuter diversion to metro corridors.",
            'action': 'Tighten network-wide baseline headways by 1.5 - 2.0 minutes during wet commute hours.',
            'type': 'weather_alert',
        })

    # Event specific recommendations
    for ev in events_used:
        nearest = ev.get('nearest_station')
        if nearest:
            corr_str = ', '.join(nearest.get('corridors', []))
            start_str = ev.get('start_time', '').split('T')[1][:5] if 'T' in ev.get('start_time', '') else ev.get('start_time', '')
            end_str = ev.get('end_time', '').split('T')[1][:5] if 'T' in ev.get('end_time', '') else ev.get('end_time', '')
            
            recommendations.append({
                'severity': 'critical' if ev.get('expected_attendance', 0) >= 30000 else 'warning',
                'corridor': corr_str,
                'message': f"Event '{ev['name']}' at {ev.get('venue_name', 'Venue')} ({start_str} - {end_str}). Est. {ev['metro_riders']:,} metro riders ({int(ev.get('metro_fraction', 0.2)*100)}% of {ev.get('expected_attendance', 0):,} attendees).",
                'action': f"Deploy extra train sets on {corr_str} Line. Compress headway to 2.2 - 3.0 min during arrival and departure windows at {nearest['stop_name']} station.",
                'type': 'event_dispatch',
            })

    # Corridor surge summary
    for corridor in corridors:
        hours_data = directional_headways[corridor]
        surge_hours = [h for h in hours_data if h['recommended_headway'] < h['baseline_headway'] - 1.2]
        if surge_hours:
            start_h = min(h['hour'] for h in surge_hours)
            end_h = max(h['hour'] for h in surge_hours)
            min_hw = min(h['recommended_headway'] for h in surge_hours)
            base_hw = round(sum(h['baseline_headway'] for h in surge_hours)/len(surge_hours), 1)
            
            recommendations.append({
                'severity': 'info',
                'corridor': f"{corridor} Line",
                'message': f"Headway compressed on {corridor} Line from baseline {base_hw} min down to {min_hw} min between {start_h}:00 and {end_h}:00.",
                'action': f"Maintain active fleet readiness on {corridor} Line during this surge window.",
                'type': 'surge_dispatch',
            })

    # Holiday & Long Weekend Dispatch Recommendations
    if holiday_info.get('bus_terminal_surge', {}).get('active'):
        recommendations.append({
            'severity': 'warning',
            'corridor': 'GREEN & RED LINES',
            'message': f"🚌 {holiday_info.get('holiday_name', 'Holiday')} Intercity Bus Terminal Rush: +{holiday_info['bus_terminal_surge']['surge_pct']}% morning crowd surge across MGBS, JBS Parade Ground, LB Nagar, and Miyapur (06:00 - 11:00 AM).",
            'action': "Deploy extra train sets on Green Line (JBS-MGBS) and Red Line to clear outbound passengers.",
            'type': 'holiday_bus_surge',
        })

    if holiday_info.get('tourist_recreation_surge', {}).get('active'):
        recommendations.append({
            'severity': 'info',
            'corridor': 'RED & BLUE LINES',
            'message': f"🏛️ Tourist & Waterfront Recreation Crowd: Expected +{holiday_info['tourist_recreation_surge']['surge_pct']}% leisure crowds at Khairatabad (Tank Bund/Hussain Sagar), Durgam Cheruvu Cable Bridge, and Shilparamam between 14:00 and 21:00.",
            'action': "Maintain tight 5.0 - 6.5 min headways on Red and Blue lines during late afternoon and evening leisure hours.",
            'type': 'holiday_tourist_surge',
        })

    # Peak fleet calculation (informational only; headways remain purely demand-driven)
    peak_fleet = 0
    peak_hour = 0
    for hour in range(5, 24):
        hour_fleet = sum(recommended.get(c, {}).get(hour, {}).get('fleet_trains', 0) for c in corridors)
        if hour_fleet > peak_fleet:
            peak_fleet = hour_fleet
            peak_hour = hour

    station_demands = {
        sid: {
            'baseline': base_demand.get(sid, {}),
            'predicted': demand.get(sid, {}),
            'event_surge': {
                h: max(0, demand.get(sid, {}).get(h, 0) - base_demand.get(sid, {}).get(h, 0))
                for h in range(5, 24)
            }
        }
        for sid in demand.keys()
    }

    return {
        'date': str(dt),
        'service_type': service_id,
        'corridors': corridors,
        'weather': weather_info,
        'holiday_info': holiday_info,
        'events_used': events_used,
        'events_excluded': events_excluded,
        'total_events': len(events_used),
        'station_demands': station_demands,
        'directional_headways': directional_headways,
        'recommendations': recommendations,
        'fleet_summary': {
            'total_fleet': FLEET_SIZE,
            'peak_fleet_needed': round(peak_fleet, 1),
            'peak_hour': peak_hour,
            'fleet_utilization_pct': round((peak_fleet / FLEET_SIZE) * 100, 1),
            'is_constrained': False,
        },
        'metro_ridership_fractions': METRO_RIDERSHIP_FRACTIONS,
    }
