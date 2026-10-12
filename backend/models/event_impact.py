import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import joblib
import numpy as np
import pandas as pd

from utils.geo import haversine_km, gaussian_decay, time_profile
from gtfs.loader import load_stops

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
VENUES_PATH = BASE_DIR / 'data' / 'venues.json'
ATTENDANCE_MODEL_PATH = BASE_DIR / 'models' / 'attendance_rf.pkl'
MODE_SHARE_MODEL_PATH = BASE_DIR / 'models' / 'mode_share_rf.pkl'

EVENT_MULTIPLIERS = {
    'cricket_international': 3.2,
    'cricket_ipl': 2.8,
    'concert': 2.2,
    'tech_summit': 1.6,
    'ganesh_procession': 2.5,
    'exhibition': 1.4,
    'political_rally': 2.0,
    'college_fest': 1.3,
    'football': 2.0,
    'other': 1.5
}

EVENT_TYPE_MAPPING = {
    'cricket_international': 'Sports',
    'cricket_ipl': 'Sports',
    'cricket': 'Sports',
    'sports': 'Sports',
    'football': 'Sports',
    'concert': 'Concert',
    'music': 'Concert',
    'tech_summit': 'Conference',
    'conference': 'Conference',
    'tech': 'Conference',
    'comedy': 'Comedy',
    'exhibition': 'Exhibition',
    'expo': 'Exhibition',
    'cultural': 'Cultural',
    'ganesh_procession': 'Cultural',
    'political_rally': 'Rally',
    'rally': 'Rally',
    'college_fest': 'Cultural',
    'other': 'Other'
}

EVENT_TYPE_ENCODING = {
    'Sports': 0,
    'Concert': 1,
    'Conference': 2,
    'Comedy': 3,
    'Exhibition': 4,
    'Cultural': 5,
    'Rally': 6,
    'Other': 7
}

_attendance_artifact = None
_mode_share_artifact = None

def _load_ml_models():
    global _attendance_artifact, _mode_share_artifact
    if _attendance_artifact is None and ATTENDANCE_MODEL_PATH.exists():
        try:
            _attendance_artifact = joblib.load(ATTENDANCE_MODEL_PATH)
        except Exception as e:
            logger.warning("Could not load attendance model: %s", e)
    if _mode_share_artifact is None and MODE_SHARE_MODEL_PATH.exists():
        try:
            _mode_share_artifact = joblib.load(MODE_SHARE_MODEL_PATH)
        except Exception as e:
            logger.warning("Could not load mode share model: %s", e)

def get_venues():
    with open(VENUES_PATH) as f:
        return json.load(f)

def predict_event_metrics(
    event_type: str,
    venue_capacity: int,
    ticket_price_avg: float = 850.0,
    user_interest_hearts: int = 15000,
    is_weekend: int = 0,
    distance_to_nearest_metro_km: float = 1.0,
    venue_parking_capacity_ratio: float = 0.15,
    event_end_hour: int = 22
) -> Dict[str, Any]:
    """
    Applies the trained Random Forest models to predict:
    1. occupancy_rate & actual_attendance
    2. metro_mode_share_pct & total_event_metro_riders
    """
    _load_ml_models()
    
    clean_cat = EVENT_TYPE_MAPPING.get(event_type.lower(), 'Other')
    cat_encoded = EVENT_TYPE_ENCODING.get(clean_cat, 7)

    # 1. Attendance prediction
    occupancy_rate = 0.45
    if _attendance_artifact is not None:
        model = _attendance_artifact['model']
        X_att = pd.DataFrame([{
            'venue_capacity': float(venue_capacity),
            'ticket_price_avg': float(ticket_price_avg),
            'user_interest_hearts': float(user_interest_hearts),
            'is_weekend': int(is_weekend),
            'event_type_encoded': cat_encoded
        }])
        try:
            pred_occ = model.predict(X_att)[0]
            occupancy_rate = float(np.clip(pred_occ, 0.08, 0.85))
        except Exception as e:
            logger.warning("Error predicting attendance: %s", e)
            occupancy_rate = 0.45

    actual_attendance = int(round(venue_capacity * occupancy_rate))

    # 2. Metro mode share prediction
    metro_mode_share_pct = 0.12
    if _mode_share_artifact is not None:
        model = _mode_share_artifact['model']
        X_mode = pd.DataFrame([{
            'distance_to_nearest_metro_km': float(distance_to_nearest_metro_km),
            'venue_parking_capacity_ratio': float(venue_parking_capacity_ratio),
            'event_end_hour': int(event_end_hour),
            'event_type_encoded': cat_encoded
        }])
        try:
            pred_ms = model.predict(X_mode)[0]
            metro_mode_share_pct = float(np.clip(pred_ms, 0.02, 0.22))
        except Exception as e:
            logger.warning("Error predicting mode share: %s", e)
            metro_mode_share_pct = 0.12

    total_event_metro_riders = int(round(actual_attendance * metro_mode_share_pct))

    return {
        'occupancy_rate': round(occupancy_rate, 4),
        'actual_attendance': actual_attendance,
        'metro_mode_share_pct': round(metro_mode_share_pct, 4),
        'total_event_metro_riders': total_event_metro_riders,
        'category': clean_cat
    }

def predict_event_impact(
    event_payload: Dict[str, Any],
    base_demands: Optional[Dict[str, Dict[int, int]]] = None
) -> Dict[str, Any]:
    """
    Phase 4 Pipeline:
    1. Ingests live event payload (e.g. from BookMyShow / upcoming_events.csv).
    2. Runs Attendance Predictor (RF) & Mode Share Predictor (RF).
    3. Calculates total_event_metro_riders.
    4. Distributes riders across metro stations based on spatial gaussian decay and time profiles.
    """
    stops = load_stops()

    # Extract event attributes with resilient fallbacks
    event_type = event_payload.get('event_type', 'other')
    venue_lat = float(event_payload.get('venue_lat', event_payload.get('lat', 17.4063)))
    venue_lon = float(event_payload.get('venue_lon', event_payload.get('lon', 78.5480)))
    venue_capacity = int(event_payload.get('venue_capacity', event_payload.get('capacity', 30000)))
    
    price_min = float(event_payload.get('ticket_price_min', 500))
    price_max = float(event_payload.get('ticket_price_max', 2500))
    ticket_price_avg = float(event_payload.get('ticket_price_avg', (price_min + price_max) / 2.0))
    user_interest_hearts = int(event_payload.get('user_interest_hearts', 20000))
    is_weekend = int(event_payload.get('is_weekend', 0))
    
    start_hour = int(event_payload.get('start_hour', 19))
    end_hour = int(event_payload.get('end_hour', 23))
    
    # Calculate nearest distance to any station for the mode share model
    dists = []
    for _, st in stops.iterrows():
        dists.append(haversine_km(st['stop_lat'], st['stop_lon'], venue_lat, venue_lon))
    dist_to_metro = min(dists) if dists else 1.0

    parking_ratio = float(event_payload.get('venue_parking_capacity_ratio', 0.12))

    # Run ML models
    metrics = predict_event_metrics(
        event_type=event_type,
        venue_capacity=venue_capacity,
        ticket_price_avg=ticket_price_avg,
        user_interest_hearts=user_interest_hearts,
        is_weekend=is_weekend,
        distance_to_nearest_metro_km=dist_to_metro,
        venue_parking_capacity_ratio=parking_ratio,
        event_end_hour=end_hour
    )

    actual_attendance = metrics['actual_attendance']
    metro_mode_share = metrics['metro_mode_share_pct']
    total_metro_riders = metrics['total_event_metro_riders']

    # Spatial-temporal distribution across stations
    station_results = {}
    
    # Weight decay over stops
    valid_stations = []
    total_decay_weight = 0.0
    for _, station in stops.iterrows():
        sid = station['stop_id']
        dist = haversine_km(station['stop_lat'], station['stop_lon'], venue_lat, venue_lon)
        decay = gaussian_decay(dist, sigma=3.5)
        if decay >= 0.01:
            valid_stations.append((sid, dist, decay))
            total_decay_weight += decay

    if total_decay_weight == 0:
        total_decay_weight = 1.0

    for sid, dist, decay in valid_stations:
        # Station share of total metro riders
        station_share = decay / total_decay_weight
        station_riders = total_metro_riders * station_share

        station_result = {}
        for hour in range(5, 24):
            # Combined ingress & egress time profile
            delta_ingress = hour - start_hour
            delta_egress = hour - end_hour
            tp_ingress = time_profile(delta_ingress)
            tp_egress = time_profile(delta_egress)
            tp = max(tp_ingress, tp_egress * 0.9)

            if tp < 0.01:
                continue

            base = 1000
            if base_demands and sid in base_demands and hour in base_demands[sid]:
                base = base_demands[sid][hour]

            # Influx based on actual predicted riders
            hourly_rider_add = round(station_riders * tp * 0.45)
            impact_pct = round((hourly_rider_add / max(base, 1)) * 100, 1)
            total = base + hourly_rider_add

            station_result[hour] = {
                'impact_pct': impact_pct,
                'absolute_increase': hourly_rider_add,
                'total_demand': total,
                'distance_km': round(dist, 2)
            }

        if station_result:
            station_results[sid] = station_result

    return {
        'ml_predictions': metrics,
        'station_impacts': station_results,
        'total_event_metro_riders': total_metro_riders,
        'actual_attendance': actual_attendance,
        'metro_mode_share_pct': metro_mode_share
    }

def calculate_event_impact(
    event_type, venue_lat, venue_lon, attendance,
    venue_capacity, start_hour, end_hour, base_demands
):
    """
    Backwards-compatible API for existing callers, now driven by ML mode share & attendance
    """
    payload = {
        'event_type': event_type,
        'venue_lat': venue_lat,
        'venue_lon': venue_lon,
        'venue_capacity': venue_capacity,
        'start_hour': start_hour,
        'end_hour': end_hour,
        'user_interest_hearts': max(5000, int(attendance * 0.9))
    }
    res = predict_event_impact(payload, base_demands=base_demands)
    return res['station_impacts']

def rank_stations_by_impact(impact_results):
    """Return top 10 most-impacted stations at peak hour."""
    station_max = []
    for sid, hours in impact_results.items():
        if not hours:
            continue
        max_pct = max(v['impact_pct'] for v in hours.values())
        peak_hour = max(hours.keys(), key=lambda h: hours[h]['impact_pct'])
        station_max.append({'station_id': sid, 'max_impact_pct': max_pct, 'peak_hour': peak_hour})
    return sorted(station_max, key=lambda x: -x['max_impact_pct'])[:10]
